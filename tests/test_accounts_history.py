import unittest

from fastapi.testclient import TestClient

from app import accounts, history, plans, tools
from app.main import app
from postgres_test_case import create_test_schema, drop_test_schema


class AccountsAndHistoryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.original_schema = create_test_schema()
        self.original_password_iterations = accounts.PASSWORD_ITERATIONS
        accounts.PASSWORD_ITERATIONS = 1_000
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        accounts.PASSWORD_ITERATIONS = self.original_password_iterations
        drop_test_schema(self.original_schema)

    def test_register_profile_logout_and_login(self):
        register = self.client.post(
            "/auth/register",
            json={"email": "Manager@Example.com", "password": "mot-de-passe"},
        )
        self.assertEqual(register.status_code, 200)
        self.assertEqual(register.json()["user"]["email"], "manager@example.com")
        self.assertEqual(self.client.get("/auth/me").status_code, 200)

        logout = self.client.post("/auth/logout")
        self.assertEqual(logout.status_code, 200)
        self.assertEqual(self.client.get("/auth/me").status_code, 401)

        login = self.client.post(
            "/auth/login",
            json={"email": "manager@example.com", "password": "mot-de-passe"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(self.client.get("/auth/me").json()["user"]["email"], "manager@example.com")

    def test_histories_are_scoped_to_connected_user(self):
        register = self.client.post(
            "/auth/register",
            json={"email": "history@example.com", "password": "mot-de-passe"},
        )
        user_id = register.json()["user"]["id"]
        plans.create_plan("plan-history", "Prépare une fiche", user_id)
        history.save_conversation(
            user_id,
            "Prépare une fiche",
            {
                "plan_id": "plan-history",
                "response": "Une action est proposée.",
                "metrics": {"total_tokens": 12},
            },
        )

        proposed = tools.execute_tool(
            "write_record",
            {"record_type": "test", "subject": "Historique", "payload": {}},
            plan_id="plan-history",
            action_index=0,
        )
        action_id = proposed["result"]["action_id"]
        history.link_actions_to_user(user_id, [{"action_id": action_id}])
        tools.approve_pending_action(action_id)

        conversations = self.client.get("/history/conversations")
        actions = self.client.get("/history/accepted-actions")
        self.assertEqual(conversations.status_code, 200)
        self.assertEqual(conversations.json()["conversations"][0]["user_message"], "Prépare une fiche")
        self.assertEqual(actions.status_code, 200)
        self.assertEqual(actions.json()["actions"][0]["id"], action_id)

        removed = self.client.delete(f"/history/accepted-actions/{action_id}")
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(
            self.client.get("/history/accepted-actions").json()["actions"],
            [],
        )
        self.assertEqual(tools.approve_pending_action(action_id)["status"], "executed")

        self.client.post("/auth/logout")
        self.assertEqual(self.client.get("/history/conversations").status_code, 401)
        self.assertEqual(self.client.get("/history/accepted-actions").status_code, 401)

    def test_duplicate_email_and_short_password_are_rejected(self):
        payload = {"email": "duplicate@example.com", "password": "mot-de-passe"}
        self.assertEqual(self.client.post("/auth/register", json=payload).status_code, 200)
        self.client.post("/auth/logout")
        self.assertEqual(self.client.post("/auth/register", json=payload).status_code, 409)
        short_password = self.client.post(
            "/auth/register",
            json={"email": "short@example.com", "password": "court"},
        )
        self.assertEqual(short_password.status_code, 422)

    def test_account_cannot_hide_another_users_accepted_action(self):
        first = self.client.post(
            "/auth/register",
            json={"email": "first@example.com", "password": "mot-de-passe"},
        ).json()["user"]
        proposed = tools.execute_tool(
            "write_record",
            {"record_type": "test", "subject": "Privé", "payload": {}},
            plan_id="plan-private-action",
        )
        action_id = proposed["result"]["action_id"]
        history.link_actions_to_user(first["id"], [{"action_id": action_id}])
        tools.approve_pending_action(action_id)
        self.client.post("/auth/logout")
        self.client.post(
            "/auth/register",
            json={"email": "second@example.com", "password": "mot-de-passe"},
        )

        response = self.client.delete(f"/history/accepted-actions/{action_id}")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
