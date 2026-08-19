import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from app import db, plans, tools
from app.main import app
from postgres_test_case import create_test_schema, drop_test_schema


class Palier4PostgreSQLTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.original_schema = create_test_schema()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        drop_test_schema(self.original_schema)

    @staticmethod
    def fake_agent_result(message: str) -> dict:
        plan_id = "plan-rechargement"
        plans.create_plan(plan_id, message)
        trace = []
        for action_index, subject in enumerate(("Poste", "Badge", "Accueil", "Suivi")):
            result = tools.execute_tool(
                "write_record",
                {
                    "record_type": "onboarding",
                    "subject": subject,
                    "payload": {"person": "Paul"},
                },
                plan_id=plan_id,
                action_index=action_index,
            )
            trace.append(
                {
                    "tool": "write_record",
                    "input": {
                        "record_type": "onboarding",
                        "subject": subject,
                        "payload": {"person": "Paul"},
                    },
                    "action_index": action_index,
                    "action_id": result["result"]["action_id"],
                    "ok": True,
                    "status": "pending",
                    "output": result["result"],
                    "error": None,
                    "latency_ms": 1,
                }
            )
        metrics = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        response = "Quatre actions attendent votre validation."
        plans.finalize_plan(plan_id, response, metrics)
        return {
            "response": response,
            "trace": trace,
            "plan_id": plan_id,
            "metrics": metrics,
        }

    def test_plan_survives_reload_with_approve_reject_and_pending_actions(self):
        with patch("app.main.run_agent", side_effect=self.fake_agent_result):
            chat = self.client.post(
                "/chat",
                json={"message": "Prépare l'arrivée de Paul"},
            )
        self.assertEqual(chat.status_code, 200)
        body = chat.json()
        self.assertEqual(len(body["trace"]), 4)
        action_ids = [step["action_id"] for step in body["trace"]]

        approved = self.client.post(f"/actions/{action_ids[0]}/approve")
        rejected = self.client.post(f"/actions/{action_ids[1]}/reject")
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(rejected.status_code, 200)

        reloaded_client = TestClient(app)
        restored = reloaded_client.get(f"/plans/{body['plan_id']}")
        reloaded_client.close()
        self.assertEqual(restored.status_code, 200)
        plan = restored.json()
        self.assertEqual(plan["user_request"], "Prépare l'arrivée de Paul")
        self.assertEqual(
            [action["status"] for action in plan["actions"]],
            ["executed", "rejected", "pending", "pending"],
        )
        self.assertEqual(plan["status"], "pending")

        replay = self.client.post(f"/actions/{action_ids[0]}/approve")
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["idempotent_replay"])
        conn = db.get_connection()
        try:
            record_count = conn.execute(
                "SELECT COUNT(*) AS total FROM records"
            ).fetchone()["total"]
            audit_count = conn.execute(
                "SELECT COUNT(*) AS total FROM audit_log"
            ).fetchone()["total"]
        finally:
            conn.close()
        self.assertEqual(record_count, 1)
        self.assertEqual(audit_count, 4)

    def test_connected_user_can_retrieve_latest_plan(self):
        registered = self.client.post(
            "/auth/register",
            json={"email": "plan@example.com", "password": "mot-de-passe"},
        )
        self.assertEqual(registered.status_code, 200)
        with patch("app.main.run_agent", side_effect=self.fake_agent_result):
            chat = self.client.post("/chat", json={"message": "Prépare quatre actions"})
        self.assertEqual(chat.status_code, 200)

        latest = self.client.get("/plans/latest")
        self.assertEqual(latest.status_code, 200)
        self.assertEqual(latest.json()["plan_id"], chat.json()["plan_id"])
        self.assertEqual(len(latest.json()["actions"]), 4)


if __name__ == "__main__":
    unittest.main()
