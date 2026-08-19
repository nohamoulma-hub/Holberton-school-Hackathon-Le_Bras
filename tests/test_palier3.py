import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app import db, tools
from postgres_test_case import create_test_schema, drop_test_schema


class Palier3TestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project_dir = Path(self.temporary_directory.name)
        self.original_schema = create_test_schema()
        self.original_project_dir = tools.PROJECT_DIR
        self.original_outbox_dir = tools.OUTBOX_DIR
        self.original_files_dir = tools.FILES_DIR
        tools.PROJECT_DIR = self.project_dir
        tools.OUTBOX_DIR = self.project_dir / "outbox"
        tools.FILES_DIR = self.project_dir / "files"

    def tearDown(self) -> None:
        tools.PROJECT_DIR = self.original_project_dir
        tools.OUTBOX_DIR = self.original_outbox_dir
        tools.FILES_DIR = self.original_files_dir
        drop_test_schema(self.original_schema)
        self.temporary_directory.cleanup()

    def queue_and_approve(
        self,
        tool_name: str,
        tool_input: dict,
        plan_id: str = "plan-test",
        action_index: int = 0,
    ):
        proposed = tools.execute_tool(
            tool_name, tool_input, plan_id=plan_id, action_index=action_index
        )
        self.assertTrue(proposed["ok"])
        self.assertEqual(proposed["status"], "pending")
        action_id = proposed["result"]["action_id"]
        executed = tools.approve_pending_action(action_id)
        self.assertTrue(executed["ok"])
        self.assertEqual(executed["status"], "executed")
        return action_id, executed

    def test_tool_registry_contains_seven_tools(self):
        expected = {
            "create_issue",
            "send_message",
            "write_record",
            "generate_document",
            "create_calendar_event",
            "list_pending_actions",
            "undo_last_action",
        }
        self.assertEqual(set(tools.TOOL_IMPLEMENTATIONS), expected)
        self.assertEqual({definition["name"] for definition in tools.TOOL_DEFINITIONS}, expected)

    def test_init_db_is_idempotent_and_creates_the_postgres_schema(self):
        db.init_db()
        db.init_db()
        conn = db.get_connection()
        try:
            tables = {
                row["table_name"]
                for row in conn.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = current_schema()
                    """
                ).fetchall()
            }
        finally:
            conn.close()
        self.assertTrue(
            {
                "users",
                "sessions",
                "plans",
                "conversations",
                "actions",
                "action_owners",
                "audit_log",
                "issues",
                "records",
                "calendar_events",
            }.issubset(tables)
        )

    def test_identical_actions_in_different_plans_are_distinct(self):
        tool_input = {
            "record_type": "incident",
            "subject": "Même contenu",
            "payload": {"severity": "low"},
        }
        first = tools.execute_tool(
            "write_record", tool_input, plan_id="plan-a", action_index=0
        )
        second = tools.execute_tool(
            "write_record", tool_input, plan_id="plan-b", action_index=0
        )
        self.assertNotEqual(first["result"]["action_id"], second["result"]["action_id"])

        conn = db.get_connection()
        keys = conn.execute(
            "SELECT idempotency_key FROM actions ORDER BY id"
        ).fetchall()
        conn.close()
        self.assertEqual(len(keys), 2)
        self.assertNotEqual(keys[0]["idempotency_key"], keys[1]["idempotency_key"])

    def test_identical_actions_at_different_indexes_are_distinct(self):
        tool_input = {
            "record_type": "incident",
            "subject": "Même contenu",
            "payload": {"severity": "low"},
        }
        first = tools.execute_tool(
            "write_record", tool_input, plan_id="plan-a", action_index=0
        )
        second = tools.execute_tool(
            "write_record", tool_input, plan_id="plan-a", action_index=1
        )
        self.assertNotEqual(first["result"]["action_id"], second["result"]["action_id"])

    def test_exact_same_action_is_an_idempotent_replay(self):
        tool_input = {
            "title": "Action idempotente",
            "description": "Ne doit être créée qu'une fois",
            "assignee": "Sophie",
            "due_date": "2026-08-25",
        }
        first = tools.execute_tool(
            "create_issue", tool_input, plan_id="plan-replay", action_index=3
        )
        replay = tools.execute_tool(
            "create_issue", tool_input, plan_id="plan-replay", action_index=3
        )
        self.assertEqual(first["result"]["action_id"], replay["result"]["action_id"])
        self.assertTrue(replay["idempotent_replay"])

        tools.approve_pending_action(first["result"]["action_id"])
        executed_replay = tools.execute_tool(
            "create_issue", tool_input, plan_id="plan-replay", action_index=3
        )
        self.assertTrue(executed_replay["idempotent_replay"])
        conn = db.get_connection()
        self.assertEqual(conn.execute("SELECT COUNT(*) AS total FROM issues").fetchone()["total"], 1)
        conn.close()

    def test_approving_the_same_action_twice_has_one_effect(self):
        proposed = tools.execute_tool(
            "write_record",
            {"record_type": "test", "subject": "Double clic", "payload": {}},
            plan_id="plan-double",
            action_index=0,
        )
        action_id = proposed["result"]["action_id"]
        first = tools.approve_pending_action(action_id)
        replay = tools.approve_pending_action(action_id)
        self.assertTrue(first["ok"])
        self.assertTrue(replay["idempotent_replay"])
        conn = db.get_connection()
        self.assertEqual(conn.execute("SELECT COUNT(*) AS total FROM records").fetchone()["total"], 1)
        conn.close()

    def test_side_effect_waits_for_approval_and_is_idempotent(self):
        tool_input = {
            "title": "Préparer le poste",
            "description": "Installer les accès nécessaires",
            "assignee": "Sophie",
            "due_date": "2026-08-25",
        }
        proposed = tools.execute_tool("create_issue", tool_input, plan_id="plan-onboarding")
        action_id = proposed["result"]["action_id"]
        conn = db.get_connection()
        self.assertEqual(conn.execute("SELECT COUNT(*) AS total FROM issues").fetchone()["total"], 0)
        conn.close()
        self.assertEqual(len(tools.list_pending_actions("plan-onboarding")), 1)

        first = tools.approve_pending_action(action_id)
        second = tools.approve_pending_action(action_id)
        self.assertTrue(first["ok"])
        self.assertTrue(second["idempotent_replay"])
        conn = db.get_connection()
        self.assertEqual(conn.execute("SELECT COUNT(*) AS total FROM issues").fetchone()["total"], 1)
        conn.close()

    def test_send_message(self):
        _, executed = self.queue_and_approve(
            "send_message",
            {"channel": "data-team", "recipient": "Équipe Data", "content": "Bienvenue Paul."},
        )
        message_path = self.project_dir / executed["result"]["path"]
        self.assertTrue(message_path.is_file())

    def test_write_record(self):
        _, executed = self.queue_and_approve(
            "write_record",
            {
                "record_type": "onboarding",
                "subject": "Paul",
                "payload": {"team": "Data", "buddy": "Sophie"},
            },
        )
        self.assertIsInstance(executed["result"]["record_id"], int)

    def test_generate_document(self):
        _, executed = self.queue_and_approve(
            "generate_document",
            {"title": "Bienvenue", "content": "Bienvenue dans l'équipe.", "filename": "paul.md"},
        )
        document_path = self.project_dir / executed["result"]["path"]
        self.assertTrue(document_path.is_file())
        self.assertIn("# Bienvenue", document_path.read_text(encoding="utf-8"))

    def test_create_calendar_event(self):
        _, executed = self.queue_and_approve(
            "create_calendar_event",
            {
                "title": "Accueil de Paul",
                "start": "2026-08-25T09:00:00+02:00",
                "duration_min": 60,
                "attendees": ["Paul", "Sophie"],
            },
        )
        self.assertIsInstance(executed["result"]["event_id"], int)

    def test_reject_does_not_execute_action(self):
        proposed = tools.execute_tool(
            "write_record",
            {"record_type": "incident", "subject": "Test", "payload": {"severity": "low"}},
            plan_id="plan-rejet",
        )
        result = tools.reject_pending_action(proposed["result"]["action_id"])
        self.assertTrue(result["ok"])
        conn = db.get_connection()
        self.assertEqual(conn.execute("SELECT COUNT(*) AS total FROM records").fetchone()["total"], 0)
        conn.close()

    def test_undo_reversible_action_once(self):
        target_action_id, executed = self.queue_and_approve(
            "write_record",
            {"record_type": "incident", "subject": "À annuler", "payload": {"status": "open"}},
        )
        undo_action_id, undone = self.queue_and_approve(
            "undo_last_action", {"action_id": str(target_action_id)}, plan_id="plan-undo"
        )
        self.assertTrue(undone["result"]["undone"])
        self.assertTrue(tools.approve_pending_action(undo_action_id)["idempotent_replay"])
        conn = db.get_connection()
        self.assertEqual(conn.execute("SELECT COUNT(*) AS total FROM records").fetchone()["total"], 0)
        status = conn.execute(
            "SELECT status FROM actions WHERE id = %s", (target_action_id,)
        ).fetchone()["status"]
        conn.close()
        self.assertEqual(status, "cancelled")

    def test_tool_errors_are_returned_and_audited(self):
        invalid = tools.execute_tool(
            "create_calendar_event",
            {"title": "Test", "start": "invalide", "duration_min": 0, "attendees": []},
            approved=True,
        )
        unknown = tools.execute_tool("outil_inconnu", {})
        self.assertFalse(invalid["ok"])
        self.assertFalse(unknown["ok"])
        conn = db.get_connection()
        self.assertEqual(
            conn.execute(
                "SELECT COUNT(*) AS total FROM audit_log WHERE status = 'error'"
            ).fetchone()["total"],
            2,
        )
        conn.close()

    def test_agent_handles_multiple_tools_and_metrics(self):
        from app import agent

        first_response = SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="tool_use",
                    id="tool-1",
                    name="create_issue",
                    input={
                        "title": "Tâche",
                        "description": "Description",
                        "assignee": "Jo",
                        "due_date": "2026-08-25",
                    },
                ),
                SimpleNamespace(
                    type="tool_use",
                    id="tool-2",
                    name="send_message",
                    input={"channel": "data", "recipient": "Équipe", "content": "Information"},
                ),
            ],
            usage=SimpleNamespace(input_tokens=12, output_tokens=8),
        )
        final_response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="Deux actions attendent une validation.")],
            usage=SimpleNamespace(input_tokens=10, output_tokens=6),
        )
        with patch.object(agent.client.messages, "create", side_effect=[first_response, final_response]):
            result = agent.run_agent("Prépare les deux actions")

        self.assertEqual(len(result["trace"]), 2)
        self.assertTrue(all(step["status"] == "pending" for step in result["trace"]))
        self.assertEqual([step["action_index"] for step in result["trace"]], [0, 1])
        self.assertEqual(result["metrics"]["total_tokens"], 36)

    def test_agent_action_index_continues_between_iterations(self):
        from app import agent

        first_response = SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="tool_use",
                    id="tool-1",
                    name="write_record",
                    input={"record_type": "test", "subject": "Premier", "payload": {}},
                )
            ],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )
        second_response = SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="tool_use",
                    id="tool-2",
                    name="write_record",
                    input={"record_type": "test", "subject": "Second", "payload": {}},
                )
            ],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )
        final_response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="Deux propositions créées.")],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )
        with patch.object(
            agent.client.messages,
            "create",
            side_effect=[first_response, second_response, final_response],
        ):
            result = agent.run_agent("Prépare deux fiches")

        self.assertEqual([step["action_index"] for step in result["trace"]], [0, 1])

    def test_agent_can_answer_without_tool(self):
        from app import agent

        response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="Je peux gérer sept outils opérationnels.")],
            usage=SimpleNamespace(input_tokens=5, output_tokens=7),
        )
        with patch.object(agent.client.messages, "create", return_value=response):
            result = agent.run_agent("Que peux-tu faire ?")
        self.assertEqual(result["trace"], [])
        self.assertIn("outils", result["response"])
        self.assertIn("ce n'est pas une action disponible", agent.SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
