# IT-Ticket_Application

Enterprise multi-tenant IT ticketing and SLA management MVP built with Flask.

## Features implemented

- Domain-based tenant isolation (`@bluvium.com`, `@abcsoft.com`, `@xyztech.com`)
- Role-aware access for `employee`, `it_support`, `manager`, and `admin`
- Ticket lifecycle status transitions (Open, In Progress, Pending, Resolved, Closed)
- SLA due-time calculation by priority and SLA health indicator (Green/Yellow/Red)
- Manager KPI endpoint for MTTR and SLA compliance

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Pass user identity with `X-User-Email` header (or `?email=` for the home page).

## API endpoints

- `POST /api/tickets`
- `GET /api/tickets`
- `PATCH /api/tickets/<ticket_id>/status`
- `GET /api/manager/kpis`
