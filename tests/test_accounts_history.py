import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import accounts, db, history, tools
from app.main import app


class AccountsAndHistoryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        self.original_password_iterations = accounts.PASSWORD_ITERATIONS
        db.DB_PATH = Path(self.temporary_directory.name) / "data.db"
        accounts.PASSWORD_ITERATIONS = 1_000
        db.init_db()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        db.DB_PATH = self.original_db_path
        accounts.PASSWORD_ITERATIONS = self.original_password_iterations
        self.temporary_directory.cleanup()

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


if __name__ == "__main__":
    unittest.main()
