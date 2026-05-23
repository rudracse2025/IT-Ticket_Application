from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from flask import Flask, abort, jsonify, render_template_string, request


SLA_POLICIES = {
    "Critical": {"response_minutes": 15, "resolution_minutes": 120},
    "High": {"response_minutes": 30, "resolution_minutes": 240},
    "Medium": {"response_minutes": 120, "resolution_minutes": 1440},
    "Low": {"response_minutes": 480, "resolution_minutes": 4320},
}

ORGANIZATIONS = {
    "bluvium.com": {"organization_id": 1, "company_name": "Bluvium Technologies"},
    "abcsoft.com": {"organization_id": 2, "company_name": "ABCSoft"},
    "xyztech.com": {"organization_id": 3, "company_name": "XYZTech"},
}

USERS = {
    "alice@bluvium.com": {"name": "Alice", "role": "employee", "department": "Engineering"},
    "bob@bluvium.com": {"name": "Bob", "role": "it_support", "department": "IT"},
    "maria@bluvium.com": {"name": "Maria", "role": "manager", "department": "Management"},
    "admin@bluvium.com": {"name": "Admin", "role": "admin", "department": "IT"},
    "eve@abcsoft.com": {"name": "Eve", "role": "employee", "department": "HR"},
}

STATUS_OPEN = "Open"
STATUS_IN_PROGRESS = "In Progress"
STATUS_PENDING = "Pending"
STATUS_RESOLVED = "Resolved"
STATUS_CLOSED = "Closed"
ALL_STATUSES = {STATUS_OPEN, STATUS_IN_PROGRESS, STATUS_PENDING, STATUS_RESOLVED, STATUS_CLOSED}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_email_domain(email: str) -> str:
    if "@" not in email:
        abort(400, "Invalid email format")
    return email.split("@", 1)[1].lower()


def get_user(email: str) -> dict[str, Any]:
    domain = parse_email_domain(email)
    if domain not in ORGANIZATIONS:
        abort(403, "Unknown organization domain")
    if email not in USERS:
        abort(403, "Unknown user")
    user = USERS[email].copy()
    user["email"] = email
    user["organization_id"] = ORGANIZATIONS[domain]["organization_id"]
    user["company_name"] = ORGANIZATIONS[domain]["company_name"]
    return user


def serialize_ticket(ticket: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or utcnow()
    result = dict(ticket)
    result["created_at"] = ticket["created_at"].isoformat()
    result["sla_due_time"] = ticket["sla_due_time"].isoformat()
    result["sla_indicator"] = get_sla_indicator(ticket, now)
    if ticket["resolved_at"] is not None:
        result["resolved_at"] = ticket["resolved_at"].isoformat()
    return result


def get_sla_indicator(ticket: dict[str, Any], now: datetime) -> str:
    if ticket["status"] in {STATUS_RESOLVED, STATUS_CLOSED}:
        return "Green"
    remaining = ticket["sla_due_time"] - now
    if remaining.total_seconds() < 0:
        return "Red"
    total = ticket["sla_due_time"] - ticket["created_at"]
    if remaining.total_seconds() <= total.total_seconds() * 0.2:
        return "Yellow"
    return "Green"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False
    app.tickets: dict[int, dict[str, Any]] = {}
    app.next_ticket_id = 1

    def current_user() -> dict[str, Any]:
        email = request.headers.get("X-User-Email") or request.args.get("email")
        if not email:
            abort(401, "Missing X-User-Email header")
        return get_user(email.strip().lower())

    def require_role(user: dict[str, Any], allowed: set[str]) -> None:
        if user["role"] not in allowed:
            allowed_roles = ", ".join(sorted(allowed))
            abort(403, f"Insufficient role. Allowed roles: {allowed_roles}")

    @app.get("/")
    def home() -> str:
        user = current_user()
        rows = []
        for ticket in app.tickets.values():
            if ticket["organization_id"] != user["organization_id"]:
                continue
            if user["role"] == "employee" and ticket["created_by"] != user["email"]:
                continue
            rows.append(serialize_ticket(ticket))
        return render_template_string(
            """
            <html>
            <head><title>Enterprise IT Service Desk</title></head>
            <body>
              <h1>Enterprise IT Service Desk & SLA Management Portal</h1>
              <p><strong>User:</strong> {{ user.email }} ({{ user.role }})</p>
              <p><strong>Organization:</strong> {{ user.company_name }}</p>
              <h2>Visible Tickets</h2>
              <table border="1" cellpadding="6" cellspacing="0">
                <tr><th>ID</th><th>Priority</th><th>Status</th><th>SLA</th><th>Category</th><th>Description</th></tr>
                {% for t in tickets %}
                <tr>
                  <td>{{ t.ticket_id }}</td>
                  <td>{{ t.priority }}</td>
                  <td>{{ t.status }}</td>
                  <td>{{ t.sla_indicator }}</td>
                  <td>{{ t.category }}</td>
                  <td>{{ t.description }}</td>
                </tr>
                {% else %}
                <tr><td colspan="6">No tickets available</td></tr>
                {% endfor %}
              </table>
            </body>
            </html>
            """,
            user=user,
            tickets=rows,
        )

    @app.post("/api/tickets")
    def create_ticket():
        user = current_user()
        require_role(user, {"employee", "it_support", "admin", "manager"})
        payload = request.get_json(silent=True) or {}
        priority = payload.get("priority", "Medium")
        category = payload.get("category", "Software")
        description = payload.get("description", "").strip()
        if priority not in SLA_POLICIES:
            abort(400, "Invalid priority")
        if not description:
            abort(400, "Description is required")
        policy = SLA_POLICIES[priority]
        created_at = utcnow()
        ticket_id = app.next_ticket_id
        app.next_ticket_id += 1
        ticket = {
            "ticket_id": ticket_id,
            "organization_id": user["organization_id"],
            "created_by": user["email"],
            "assigned_to": None,
            "priority": priority,
            "status": STATUS_OPEN,
            "category": category,
            "description": description,
            "created_at": created_at,
            "resolved_at": None,
            "sla_due_time": created_at + timedelta(minutes=policy["resolution_minutes"]),
        }
        app.tickets[ticket_id] = ticket
        return jsonify(serialize_ticket(ticket)), 201

    @app.get("/api/tickets")
    def list_tickets():
        user = current_user()
        tickets = []
        for ticket in app.tickets.values():
            if ticket["organization_id"] != user["organization_id"]:
                continue
            if user["role"] == "employee" and ticket["created_by"] != user["email"]:
                continue
            tickets.append(serialize_ticket(ticket))
        return jsonify({"tickets": tickets})

    @app.patch("/api/tickets/<int:ticket_id>/status")
    def update_ticket_status(ticket_id: int):
        user = current_user()
        require_role(user, {"it_support", "admin"})
        if ticket_id not in app.tickets:
            abort(404, "Ticket not found")
        ticket = app.tickets[ticket_id]
        if ticket["organization_id"] != user["organization_id"]:
            abort(404, "Ticket not found")
        payload = request.get_json(silent=True) or {}
        status = payload.get("status")
        if status not in ALL_STATUSES:
            abort(400, "Invalid status")
        ticket["status"] = status
        if status in {STATUS_RESOLVED, STATUS_CLOSED}:
            ticket["resolved_at"] = utcnow()
        return jsonify(serialize_ticket(ticket))

    @app.get("/api/manager/kpis")
    def manager_kpis():
        user = current_user()
        require_role(user, {"manager", "admin"})
        now = utcnow()
        org_tickets = [t for t in app.tickets.values() if t["organization_id"] == user["organization_id"]]
        total = len(org_tickets)
        closed = len([t for t in org_tickets if t["status"] in {STATUS_RESOLVED, STATUS_CLOSED}])
        open_count = len([t for t in org_tickets if t["status"] == STATUS_OPEN])
        breached = len([t for t in org_tickets if get_sla_indicator(t, now) == "Red"])
        resolved = [t for t in org_tickets if t["resolved_at"] is not None]
        mttr_minutes = 0.0
        if resolved:
            mttr_minutes = sum(
                (t["resolved_at"] - t["created_at"]).total_seconds() / 60 for t in resolved
            ) / len(resolved)
        sla_compliance = 100.0
        if total:
            sla_compliance = ((total - breached) / total) * 100.0
        return jsonify(
            {
                "total_tickets": total,
                "open_tickets": open_count,
                "closed_tickets": closed,
                "sla_breach_percentage": round((breached / total) * 100.0, 2) if total else 0.0,
                "sla_compliance_percentage": round(sla_compliance, 2),
                "mttr_minutes": round(mttr_minutes, 2),
            }
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run()
