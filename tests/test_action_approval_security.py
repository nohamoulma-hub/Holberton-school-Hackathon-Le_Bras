import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import accounts, plans, tools
from app.db import get_connection
from app.main import app
from postgres_test_case import create_test_schema, drop_test_schema


class ActionApprovalSecurityTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.original_schema = create_test_schema()
        self.original_password_iterations = accounts.PASSWORD_ITERATIONS
        accounts.PASSWORD_ITERATIONS = 1_000
        self.clients: list[TestClient] = []

    def tearDown(self) -> None:
        for client in self.clients:
            client.close()
        accounts.PASSWORD_ITERATIONS = self.original_password_iterations
        drop_test_schema(self.original_schema)

    def client_for(self, email: str) -> tuple[TestClient, dict]:
        client = TestClient(app)
        self.clients.append(client)
        response = client.post(
            "/auth/register",
            json={"email": email, "password": "mot-de-passe"},
        )
        self.assertEqual(response.status_code, 200)
        return client, response.json()["user"]

    @staticmethod
    def action_status(action_id: int) -> str:
        conn = get_connection()
        try:
            return conn.execute(
                "SELECT status FROM actions WHERE id = %s", (action_id,)
            ).fetchone()["status"]
        finally:
            conn.close()

    @staticmethod
    def table_count(table_name: str) -> int:
        if table_name not in {"issues", "records"}:
            raise ValueError("Table de test non autorisée")
        conn = get_connection()
        try:
            return conn.execute(
                f"SELECT COUNT(*) AS total FROM {table_name}"
            ).fetchone()["total"]
        finally:
            conn.close()

    @staticmethod
    def propose_issue(plan_id: str, action_index: int = 0) -> int:
        result = tools.execute_tool(
            "create_issue",
            {
                "title": "Action protégée",
                "description": "Vérifier le propriétaire",
                "assignee": "Équipe",
                "due_date": "2026-08-25",
            },
            plan_id=plan_id,
            action_index=action_index,
        )
        return result["result"]["action_id"]

    def test_another_user_cannot_approve_owned_action(self):
        _, owner = self.client_for("approve-owner@example.com")
        other_client, _ = self.client_for("approve-other@example.com")
        plans.create_plan("owned-approve", "Action privée", owner["id"])
        action_id = self.propose_issue("owned-approve")

        response = other_client.post(f"/actions/{action_id}/approve")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.table_count("issues"), 0)
        self.assertEqual(self.action_status(action_id), "pending")

    def test_another_user_cannot_reject_owned_action(self):
        _, owner = self.client_for("reject-owner@example.com")
        other_client, _ = self.client_for("reject-other@example.com")
        plans.create_plan("owned-reject", "Action privée", owner["id"])
        action_id = self.propose_issue("owned-reject")

        response = other_client.post(f"/actions/{action_id}/reject")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.action_status(action_id), "pending")

    def test_owner_can_approve_and_reject_own_actions(self):
        owner_client, owner = self.client_for("decision-owner@example.com")
        plans.create_plan("owner-decisions", "Deux décisions", owner["id"])
        approved_id = self.propose_issue("owner-decisions", 0)
        rejected_id = self.propose_issue("owner-decisions", 1)

        approved = owner_client.post(f"/actions/{approved_id}/approve")
        rejected = owner_client.post(f"/actions/{rejected_id}/reject")

        self.assertEqual(approved.status_code, 200)
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(self.table_count("issues"), 1)
        self.assertEqual(self.action_status(approved_id), "executed")
        self.assertEqual(self.action_status(rejected_id), "rejected")

    def test_anonymous_plan_can_still_be_approved_and_rejected(self):
        client = TestClient(app)
        self.clients.append(client)
        plans.create_plan("anonymous-decisions", "Deux décisions anonymes")
        approved_id = self.propose_issue("anonymous-decisions", 0)
        rejected_id = self.propose_issue("anonymous-decisions", 1)

        approved = client.post(f"/actions/{approved_id}/approve")
        rejected = client.post(f"/actions/{rejected_id}/reject")

        self.assertEqual(approved.status_code, 200)
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(self.table_count("issues"), 1)
        self.assertEqual(self.action_status(approved_id), "executed")
        self.assertEqual(self.action_status(rejected_id), "rejected")

    def test_tool_failure_after_claim_marks_action_as_error(self):
        result = tools.execute_tool(
            "undo_last_action",
            {"action_id": "999999999"},
            plan_id="failing-approval",
            action_index=0,
        )
        action_id = result["result"]["action_id"]

        approved = tools.approve_pending_action(action_id)

        self.assertFalse(approved["ok"])
        self.assertEqual(approved["status"], "error")
        self.assertIn("Action introuvable", approved["error"])
        self.assertEqual(self.action_status(action_id), "error")

    def assert_concurrent_approval_has_one_effect(
        self,
        tool_name: str,
        arguments: dict,
        table_name: str,
    ) -> None:
        result = tools.execute_tool(
            tool_name,
            arguments,
            plan_id=f"concurrent-{tool_name}",
            action_index=0,
        )
        action_id = result["result"]["action_id"]
        original_implementation = tools.TOOL_IMPLEMENTATIONS[tool_name]

        def slow_implementation(**tool_input):
            time.sleep(0.15)
            return original_implementation(**tool_input)

        barrier = Barrier(2)

        def approve():
            barrier.wait()
            return tools.approve_pending_action(action_id)

        with patch.dict(
            tools.TOOL_IMPLEMENTATIONS,
            {tool_name: slow_implementation},
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(executor.map(lambda _: approve(), range(2)))

        self.assertEqual(self.table_count(table_name), 1)
        self.assertEqual(self.action_status(action_id), "executed")
        self.assertEqual(sum(response["ok"] for response in responses), 1)
        self.assertIn("déjà executing", next(
            response["error"] for response in responses if not response["ok"]
        ))

    def test_concurrent_issue_approval_has_one_effect(self):
        self.assert_concurrent_approval_has_one_effect(
            "create_issue",
            {
                "title": "Issue concurrente",
                "description": "Une seule insertion",
                "assignee": "Équipe",
                "due_date": "2026-08-25",
            },
            "issues",
        )

    def test_concurrent_record_approval_has_one_effect(self):
        self.assert_concurrent_approval_has_one_effect(
            "write_record",
            {
                "record_type": "concurrency-test",
                "subject": "Record concurrent",
                "payload": {"expected": 1},
            },
            "records",
        )


if __name__ == "__main__":
    unittest.main()
