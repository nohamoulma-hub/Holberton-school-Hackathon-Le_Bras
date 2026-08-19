import json
import os
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app import agent, db, plans, tools
from app.main import app
from postgres_test_case import create_test_schema, drop_test_schema


def tool_response(identifier: str, name: str, tool_input: dict) -> SimpleNamespace:
    """Construit une réponse Anthropic simulée contenant un appel de Tool."""
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="tool_use", id=identifier, name=name, input=tool_input)
        ],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


def text_response(text: str = "Terminé.") -> SimpleNamespace:
    """Construit une réponse Anthropic simulée qui conclut la boucle Agent."""
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=4, output_tokens=2),
    )


class Palier4RegressionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.original_schema = create_test_schema()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.project_dir = Path(self.temporary_directory.name)
        self.original_project_dir = tools.PROJECT_DIR
        self.original_outbox_dir = tools.OUTBOX_DIR
        self.original_files_dir = tools.FILES_DIR
        tools.PROJECT_DIR = self.project_dir
        tools.OUTBOX_DIR = self.project_dir / "outbox"
        tools.FILES_DIR = self.project_dir / "files"
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        tools.PROJECT_DIR = self.original_project_dir
        tools.OUTBOX_DIR = self.original_outbox_dir
        tools.FILES_DIR = self.original_files_dir
        drop_test_schema(self.original_schema)
        self.temporary_directory.cleanup()

    def action_count(self) -> int:
        """Retourne le nombre d'actions du schéma isolé courant."""
        conn = db.get_connection()
        try:
            return conn.execute("SELECT COUNT(*) AS total FROM actions").fetchone()["total"]
        finally:
            conn.close()

    def test_list_pending_twice_is_json_serializable_and_audited(self):
        tools.execute_tool(
            "write_record",
            {"record_type": "test", "subject": "À valider", "payload": {}},
            plan_id="plan-liste",
        )
        first = tools.execute_tool(
            "list_pending_actions", {"plan_id": "plan-liste"}, plan_id="plan-liste"
        )
        second = tools.execute_tool(
            "list_pending_actions", {"plan_id": "plan-liste"}, plan_id="plan-liste"
        )
        json.dumps(first)
        json.dumps(second)
        self.assertEqual(first["result"][0]["status"], "pending")
        conn = db.get_connection()
        try:
            audits = conn.execute(
                "SELECT COUNT(*) AS total FROM audit_log WHERE tool_name = %s",
                ("list_pending_actions",),
            ).fetchone()["total"]
        finally:
            conn.close()
        self.assertEqual(audits, 1)

    def test_list_pending_agent_loop_returns_without_http_500(self):
        responses = [
            tool_response(
                "one",
                "write_record",
                {"record_type": "test", "subject": "Liste", "payload": {}},
            ),
            tool_response("two", "list_pending_actions", {"plan_id": "plan-agent-list"}),
            text_response("La boucle continue après la consultation."),
        ]
        with (
            patch.object(agent.uuid, "uuid4", return_value=SimpleNamespace(hex="plan-agent-list")),
            patch.object(agent.client.messages, "create", side_effect=responses),
        ):
            response = self.client.post("/chat", json={"message": "Liste le plan"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["trace"]), 2)
        self.assertTrue(response.json()["trace"][1]["ok"])

    def test_send_message_without_content_is_rejected_before_pending(self):
        result = tools.execute_tool(
            "send_message",
            {"channel": "general", "recipient": "Équipe"},
            plan_id="plan-message-invalide",
        )
        self.assertFalse(result["ok"])
        self.assertIn("content", result["error"])
        self.assertEqual(self.action_count(), 0)

    def test_generate_document_without_content_is_rejected_before_pending(self):
        result = tools.execute_tool(
            "generate_document",
            {"title": "Document", "filename": "document.md"},
            plan_id="plan-document-invalide",
        )
        self.assertFalse(result["ok"])
        self.assertIn("content", result["error"])
        self.assertEqual(self.action_count(), 0)

    def test_additional_argument_is_rejected_by_declared_schema(self):
        result = tools.execute_tool(
            "write_record",
            {"record_type": "test", "subject": "Sujet", "payload": {}, "extra": True},
            plan_id="plan-extra",
        )
        self.assertFalse(result["ok"])
        self.assertIn("supplémentaire", result["error"])

    def test_invalid_calendar_action_is_absent_from_actions_table(self):
        result = tools.execute_tool(
            "create_calendar_event",
            {"title": "Invalide", "start": "demain", "duration_min": 0, "attendees": []},
            plan_id="plan-calendrier-invalide",
        )
        self.assertFalse(result["ok"])
        self.assertEqual(self.action_count(), 0)

    def test_agent_receives_validation_error_then_corrects_next_turn(self):
        responses = [
            tool_response(
                "invalid",
                "send_message",
                {"channel": "general", "recipient": "Équipe"},
            ),
            tool_response(
                "corrected",
                "send_message",
                {"channel": "general", "recipient": "Équipe", "content": "Bonjour."},
            ),
            text_response("Le message corrigé attend une validation."),
        ]
        with patch.object(agent.client.messages, "create", side_effect=responses) as create:
            result = agent.run_agent("Prépare un message")
        self.assertEqual(create.call_count, 3)
        self.assertFalse(result["trace"][0]["ok"])
        self.assertIsNone(result["trace"][0]["action_id"])
        self.assertEqual(result["trace"][1]["status"], "pending")
        self.assertEqual(self.action_count(), 1)

    def test_valid_action_still_becomes_pending(self):
        result = tools.execute_tool(
            "write_record",
            {"record_type": "test", "subject": "Valide", "payload": {}},
            plan_id="plan-valide",
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "pending")
        self.assertEqual(self.action_count(), 1)

    def test_approval_remains_idempotent_after_schema_validation(self):
        pending = tools.execute_tool(
            "write_record",
            {"record_type": "test", "subject": "Idempotence", "payload": {}},
            plan_id="plan-idempotent",
        )
        action_id = pending["result"]["action_id"]
        first = tools.approve_pending_action(action_id)
        second = tools.approve_pending_action(action_id)
        self.assertTrue(first["ok"])
        self.assertTrue(second["idempotent_replay"])

    def test_plan_restoration_preserves_mixed_action_statuses(self):
        plan_id = "plan-f5-regression"
        plans.create_plan(plan_id, "Teste le rechargement")
        action_ids = []
        for index, subject in enumerate(("Exécutée", "Refusée", "Pending")):
            pending = tools.execute_tool(
                "write_record",
                {"record_type": "test", "subject": subject, "payload": {}},
                plan_id=plan_id,
                action_index=index,
            )
            action_ids.append(pending["result"]["action_id"])
        tools.approve_pending_action(action_ids[0])
        tools.reject_pending_action(action_ids[1])
        plans.finalize_plan(plan_id, "Plan prêt.", {"total_tokens": 1})
        restored = self.client.get(f"/plans/{plan_id}")
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(
            [item["status"] for item in restored.json()["actions"]],
            ["executed", "rejected", "pending"],
        )

    def test_calendar_endpoint_still_returns_executed_event(self):
        pending = tools.execute_tool(
            "create_calendar_event",
            {
                "title": "Bilan",
                "start": "2026-08-25T10:00:00+02:00",
                "duration_min": 60,
                "attendees": ["Alice"],
            },
            plan_id="plan-calendrier",
        )
        tools.approve_pending_action(pending["result"]["action_id"])
        response = self.client.get("/calendar/events?start=2026-08-01&end=2026-08-31")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["events"][0]["title"], "Bilan")

    def test_relative_date_context_remains_available(self):
        current = datetime(2026, 8, 19, 9, 0, tzinfo=ZoneInfo("Europe/Paris"))
        with (
            patch.object(agent, "get_current_datetime", return_value=current),
            patch.object(agent.client.messages, "create", return_value=text_response()) as create,
        ):
            agent.run_agent("Planifie demain")
        self.assertIn("date actuelle : 2026-08-19", create.call_args.kwargs["system"])

    def test_agent_guard_stops_after_four_tool_iterations(self):
        looping_response = tool_response(
            "loop", "list_pending_actions", {"plan_id": "plan-garde"}
        )
        with (
            patch.object(agent.uuid, "uuid4", return_value=SimpleNamespace(hex="plan-garde")),
            patch.object(
                agent.client.messages,
                "create",
                side_effect=[looping_response] * agent.MAX_TOOL_ITERATIONS,
            ) as create,
        ):
            result = agent.run_agent("Continue sans fin")
        self.assertEqual(create.call_count, 4)
        self.assertIn("Trop d'itérations", result["response"])

    def test_agent_metrics_keep_token_latency_and_cost_fields(self):
        response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="Réponse")],
            usage=SimpleNamespace(input_tokens=100, output_tokens=50),
        )
        with patch.object(agent.client.messages, "create", return_value=response):
            metrics = agent.run_agent("Mesure")["metrics"]
        self.assertEqual(metrics["total_tokens"], 150)
        self.assertIsInstance(metrics["latency_ms"], float)
        self.assertEqual(metrics["cost_status"], "estimated")

    def test_estimated_cost_matches_sonnet_5_token_prices(self):
        metrics = agent._metrics(1_000_000, 1_000_000, time.monotonic())
        self.assertEqual(metrics["estimated_cost"], 18.0)
        self.assertEqual(agent.INPUT_PRICE_PER_MILLION_USD, 3.0)
        self.assertEqual(agent.OUTPUT_PRICE_PER_MILLION_USD, 15.0)


if __name__ == "__main__":
    unittest.main()
