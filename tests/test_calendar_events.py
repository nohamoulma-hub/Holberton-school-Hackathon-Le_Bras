import unittest

from fastapi.testclient import TestClient

from app import db, tools
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
            params={"start": "2026-08-01", "end": "2026-09-01"},
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
            "/calendar/events?start=2026-08-01&end=2026-09-01"
        )
        september = self.client.get(
            "/calendar/events?start=2026-09-01&end=2026-10-01"
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

        conn = db.get_connection()
        try:
            count = conn.execute(
                "SELECT COUNT(*) AS total FROM calendar_events"
            ).fetchone()["total"]
        finally:
            conn.close()
        self.assertEqual(count, 0)
        self.assertEqual(self.client.get("/calendar/events").json()["events"], [])


if __name__ == "__main__":
    unittest.main()
