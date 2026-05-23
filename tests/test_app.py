import unittest
from datetime import timedelta

from app import create_app, utcnow


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
        created = self.create_ticket("alice@bluvium.com")
        ticket_id = created.get_json()["ticket_id"]
        ticket = self.app.tickets[ticket_id]

        ticket["created_at"] = utcnow() - timedelta(hours=3, minutes=50)
        ticket["sla_due_time"] = ticket["created_at"] + timedelta(hours=4)

        near_breach = self.client.get("/api/tickets", headers={"X-User-Email": "bob@bluvium.com"})
        self.assertEqual(near_breach.get_json()["tickets"][0]["sla_indicator"], "Yellow")

        ticket["sla_due_time"] = utcnow() - timedelta(minutes=1)
        breached = self.client.get("/api/tickets", headers={"X-User-Email": "bob@bluvium.com"})
        self.assertEqual(breached.get_json()["tickets"][0]["sla_indicator"], "Red")


if __name__ == "__main__":
    unittest.main()
