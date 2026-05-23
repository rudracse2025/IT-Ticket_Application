import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app import create_app


class TicketingAppTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def create_ticket(self, email: str, description: str = "VPN not connecting"):
        return self.client.post(
            "/api/tickets",
            headers={"X-User-Email": email},
            json={"priority": "High", "category": "VPN Issues", "description": description},
        )

    def test_multi_tenant_isolation_between_organizations(self):
        create_response = self.create_ticket("alice@bluvium.com")
        self.assertEqual(create_response.status_code, 201)

        list_response = self.client.get("/api/tickets", headers={"X-User-Email": "eve@abcsoft.com"})
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.get_json()["tickets"], [])

    def test_employee_cannot_update_ticket_status(self):
        created = self.create_ticket("alice@bluvium.com")
        ticket_id = created.get_json()["ticket_id"]

        update = self.client.patch(
            f"/api/tickets/{ticket_id}/status",
            headers={"X-User-Email": "alice@bluvium.com"},
            json={"status": "In Progress"},
        )
        self.assertEqual(update.status_code, 403)

    def test_sla_indicator_changes_from_yellow_to_red(self):
        base_time = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
        with patch("app.utcnow", return_value=base_time):
            created = self.create_ticket("alice@bluvium.com")
            self.assertEqual(created.status_code, 201)

        with patch("app.utcnow", return_value=base_time + timedelta(hours=3, minutes=50)):
            near_breach = self.client.get("/api/tickets", headers={"X-User-Email": "bob@bluvium.com"})
        self.assertEqual(near_breach.get_json()["tickets"][0]["sla_indicator"], "Yellow")

        with patch("app.utcnow", return_value=base_time + timedelta(hours=4, minutes=1)):
            breached = self.client.get("/api/tickets", headers={"X-User-Email": "bob@bluvium.com"})
        self.assertEqual(breached.get_json()["tickets"][0]["sla_indicator"], "Red")

    def test_manager_kpis_include_mttr_and_sla_metrics(self):
        base_time = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
        with patch("app.utcnow", return_value=base_time):
            first = self.create_ticket("alice@bluvium.com", "Email issue")
            second = self.create_ticket("alice@bluvium.com", "Access issue")
            self.assertEqual(first.status_code, 201)
            self.assertEqual(second.status_code, 201)

        ticket_id = first.get_json()["ticket_id"]
        with patch("app.utcnow", return_value=base_time + timedelta(hours=1)):
            resolve = self.client.patch(
                f"/api/tickets/{ticket_id}/status",
                headers={"X-User-Email": "bob@bluvium.com"},
                json={"status": "Resolved"},
            )
        self.assertEqual(resolve.status_code, 200)

        with patch("app.utcnow", return_value=base_time + timedelta(hours=5)):
            kpis = self.client.get("/api/manager/kpis", headers={"X-User-Email": "maria@bluvium.com"})
        self.assertEqual(kpis.status_code, 200)
        body = kpis.get_json()
        self.assertEqual(body["total_tickets"], 2)
        self.assertEqual(body["closed_tickets"], 1)
        self.assertEqual(body["open_tickets"], 1)
        self.assertEqual(body["mttr_minutes"], 60.0)
        self.assertEqual(body["sla_breach_percentage"], 50.0)
        self.assertEqual(body["sla_compliance_percentage"], 50.0)


if __name__ == "__main__":
    unittest.main()
