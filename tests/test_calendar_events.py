import unittest

from fastapi.testclient import TestClient

from app import db, history, tools
from app.main import app
from postgres_test_case import create_test_schema, drop_test_schema


class CalendarEventsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.original_schema = create_test_schema()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        drop_test_schema(self.original_schema)

    @staticmethod
    def propose_event(
        action_index: int,
        title: str,
        start: str,
        attendees: list[str],
    ) -> int:
        result = tools.execute_tool(
            "create_calendar_event",
            {
                "title": title,
                "start": start,
                "duration_min": 60,
                "attendees": attendees,
            },
            plan_id="plan-calendar",
            action_index=action_index,
        )
        return result["result"]["action_id"]

    def test_only_executed_events_are_visible_and_attendees_are_decoded(self):
        executed_id = self.propose_event(
            0,
            "Réunion d'équipe",
            "2026-08-22T10:00:00+02:00",
            ["Bertrand"],
        )
        rejected_id = self.propose_event(
            1,
            "Événement refusé",
            "2026-08-23T10:00:00+02:00",
            ["Sophie"],
        )
        self.propose_event(
            2,
            "Événement en attente",
            "2026-08-24T10:00:00+02:00",
            ["Paul"],
        )
        tools.approve_pending_action(executed_id)
        tools.reject_pending_action(rejected_id)

        response = self.client.get(
            "/calendar/events",
            params={
                "start": "2026-08-01",
                "end": "2026-09-01",
                "plan_id": "plan-calendar",
            },
        )
        self.assertEqual(response.status_code, 200)
        events = response.json()["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["title"], "Réunion d'équipe")
        self.assertEqual(events[0]["start"], "2026-08-22T10:00:00+02:00")
        self.assertEqual(events[0]["duration_min"], 60)
        self.assertEqual(events[0]["attendees"], ["Bertrand"])

    def test_period_filter_excludes_events_from_another_month(self):
        august_id = self.propose_event(
            0,
            "Réunion août",
            "2026-08-22T10:00:00+02:00",
            ["Bertrand"],
        )
        september_id = self.propose_event(
            1,
            "Réunion septembre",
            "2026-09-03T14:00:00+02:00",
            ["Sophie", "Paul"],
        )
        tools.approve_pending_action(august_id)
        tools.approve_pending_action(september_id)

        august = self.client.get(
            "/calendar/events?start=2026-08-01&end=2026-09-01&plan_id=plan-calendar"
        )
        september = self.client.get(
            "/calendar/events?start=2026-09-01&end=2026-10-01&plan_id=plan-calendar"
        )
        self.assertEqual(
            [event["title"] for event in august.json()["events"]],
            ["Réunion août"],
        )
        self.assertEqual(
            [event["title"] for event in september.json()["events"]],
            ["Réunion septembre"],
        )

    def test_invalid_period_is_rejected(self):
        response = self.client.get(
            "/calendar/events?start=2026-09-01&end=2026-08-01"
        )
        self.assertEqual(response.status_code, 422)

    def test_pending_and_rejected_actions_create_no_calendar_row(self):
        rejected_id = self.propose_event(
            0,
            "Refusé",
            "2026-08-22T10:00:00+02:00",
            ["Bertrand"],
        )
        self.propose_event(
            1,
            "En attente",
            "2026-08-23T10:00:00+02:00",
            ["Sophie"],
        )
        tools.reject_pending_action(rejected_id)

        self.assertEqual(
            self.client.get(
                "/calendar/events?plan_id=plan-calendar"
            ).json()["events"],
            [],
        )
    def test_delete_event_removes_it_and_cancels_its_action(self):
        action_id = self.propose_event(
            0,
            "Événement à supprimer",
            "2026-08-25T10:00:00+02:00",
            ["Sophie"],
        )
        approved = tools.approve_pending_action(action_id)
        event_id = approved["result"]["event_id"]

        response = self.client.delete(
            f"/calendar/events/{event_id}?plan_id=plan-calendar"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "deleted")
        self.assertEqual(response.json()["action_id"], action_id)
        self.assertEqual(
            self.client.get(
                "/calendar/events?plan_id=plan-calendar"
            ).json()["events"],
            [],
        )
        conn = db.get_connection()
        try:
            action_status = conn.execute(
                "SELECT status FROM actions WHERE id = %s", (action_id,)
            ).fetchone()["status"]
            audit_status = conn.execute(
                "SELECT status FROM audit_log WHERE tool_name = 'create_calendar_event'"
            ).fetchone()["status"]
        finally:
            conn.close()
        self.assertEqual(action_status, "cancelled")
        self.assertEqual(audit_status, "cancelled")

    def test_delete_unknown_event_returns_404(self):
        response = self.client.delete("/calendar/events/999999")
        self.assertEqual(response.status_code, 404)

    def test_anonymous_calendar_requires_a_known_local_plan(self):
        action_id = self.propose_event(
            0,
            "Événement anonyme",
            "2026-08-25T10:00:00+02:00",
            ["Sophie"],
        )
        tools.approve_pending_action(action_id)

        self.assertEqual(self.client.get("/calendar/events").json()["events"], [])
        own_events = self.client.get(
            "/calendar/events?plan_id=plan-calendar"
        ).json()["events"]
        self.assertEqual([event["title"] for event in own_events], ["Événement anonyme"])

    def test_connected_calendar_is_scoped_to_its_account(self):
        first_user = self.client.post(
            "/auth/register",
            json={"email": "calendar-one@example.com", "password": "mot-de-passe"},
        ).json()["user"]
        first_action = self.propose_event(
            0,
            "Événement du premier compte",
            "2026-08-25T10:00:00+02:00",
            ["Alice"],
        )
        history.link_actions_to_user(first_user["id"], [{"action_id": first_action}])
        first_result = tools.approve_pending_action(first_action)
        first_event_id = first_result["result"]["event_id"]
        self.assertEqual(len(self.client.get("/calendar/events").json()["events"]), 1)

        self.client.post("/auth/logout")
        self.client.post(
            "/auth/register",
            json={"email": "calendar-two@example.com", "password": "mot-de-passe"},
        )

        self.assertEqual(self.client.get("/calendar/events").json()["events"], [])
        self.assertEqual(
            self.client.delete(f"/calendar/events/{first_event_id}").status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
