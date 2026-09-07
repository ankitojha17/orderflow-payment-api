# OrderFlow - Order & Payment Management API

Order and payment management API — Django REST Framework, PostgreSQL, Redis, Celery, and Razorpay (test mode).
Runs entirely in Docker: `docker-compose up` starts the API, database, cache/broker, and background worker together.

---

## Architecture decisions (read this before diving into the code)

- **Business logic lives in views, not serializers.** Serializers only validate input — checking negative cases first (duplicate items, missing product, insufficient stock) — and never write to the database. The actual order creation, stock locking, and total calculation happen in `CreateOrderView._create_order()`. This mirrors the pattern used in production Django REST projects where views own the workflow and serializers own the shape/validity of data.
- **`select_for_update()` + `transaction.atomic()`** in `CreateOrderView` lock each `Product` row for the duration of the order-creation transaction, preventing two concurrent requests from overselling the same stock.
- **`select_related` / `prefetch_related`** are used on every list/detail view that touches related objects (`Order.user`, `OrderItem.product`), avoiding N+1 queries.
- **The Razorpay webhook is `csrf_exempt`** — it's a server-to-server call from Razorpay, not a browser session, so there's no CSRF token to check. Authenticity instead comes from HMAC signature verification (`X-Razorpay-Signature`).
- **Idempotency** is handled at the one place it actually matters: `Payment.is_webhook_processed` prevents a duplicate Razorpay webhook delivery from double-processing a payment. This project intentionally does not implement a generic client-facing idempotency-key system — that's out of scope for this project's size.
- **Celery + Redis** run the confirmation email off the request/response cycle. The webhook queues `send_order_confirmation_email_task.delay(...)` and returns immediately rather than blocking on email I/O.

---

## Tech stack
Python, Django, Django REST Framework, PostgreSQL, Redis, Celery, Razorpay, Docker, django-filter, drf-yasg (Swagger/OpenAPI), PyJWT

---

## Running it (Docker only — this is the intended workflow)

```bash
cp .env.example .env
# open .env and set real values for DJANGO_SECRET_KEY, JWT_SECRET_KEY,
# and your Razorpay test-mode keys

docker-compose up --build
```

This starts four containers:
- `web` — Django, on http://localhost:8000
- `db` — PostgreSQL
- `redis` — cache + Celery broker
- `celery_worker` — processes the confirmation-email task

Migrations run automatically on container start (see `entrypoint.sh`).

Create an admin user (in a second terminal, once containers are up):
```bash
docker-compose exec web python manage.py createsuperuser
```

- Swagger UI: **http://localhost:8000/swagger/**
- Django admin: **http://localhost:8000/admin/**

---

## Authenticating in Swagger
1. `POST /api/auth/register/` to create an account, or use your superuser
2. `POST /api/auth/login/` with username/password — copy the `token` from the response
3. Click **Authorize** in Swagger, paste in: `Bearer <token>` (the word "Bearer", a space, then the token)

---

## Testing with Postman

There's no exported Postman collection in this repo (Swagger above covers most manual testing needs),
but if you prefer Postman:
1. Base URL: `http://localhost:8000/api`
2. `POST {{base_url}}/auth/register/` → body (raw JSON): `{"username": "...", "email": "...", "password": "..."}`
3. `POST {{base_url}}/auth/login/` → copy `data.token` from the response
4. On every authenticated request, add header `Authorization: Bearer <token>` (Postman's **Bearer Token**
   auth type under a request's **Authorization** tab does this for you — just paste the raw token, no
   need to type "Bearer" yourself).
5. For `/orders/<id>/pay/`, use Razorpay **test-mode** keys in `.env` — no real charge is made.
6. The `/webhook/razorpay/` endpoint expects an `X-Razorpay-Signature` header (HMAC-SHA256 of the raw
   body using `RAZORPAY_WEBHOOK_SECRET`) — it's meant to be called by Razorpay itself, not tested
   manually from Postman unless you replicate that signature.

---

## API endpoints

| Method | Endpoint | Auth | Notes |
|---|---|---|---|
| POST | `/api/auth/register/` | No | |
| POST | `/api/auth/login/` | No | Returns a JWT |
| GET | `/api/products/` | No | `?search=<name>`, paginated |
| POST | `/api/orders/` | Bearer | `{items: [{product_id, quantity}]}` |
| GET | `/api/orders/list/` | Bearer | `?status=paid`, paginated |
| GET | `/api/orders/<id>/` | Bearer | |
| POST | `/api/orders/<id>/pay/` | Bearer | Creates a Razorpay order |
| POST | `/api/webhook/razorpay/` | No (Razorpay calls this) | Verifies signature, marks order paid, queues email |

Paginated responses include a `meta` block: `{page, page_size, total, total_pages}`.

---

## Project structure

```
services/
├── models/              one file per model
├── serializer/           validation only — negative cases checked first, no DB writes
├── views/                 business logic lives here, class-based
│   ├── auth/                register, login
│   ├── orders/               create (atomic + select_for_update), detail, list
│   └── payments/              create payment, Razorpay webhook (csrf_exempt)
├── utils/                response_handler.py, authentication.py (Bearer JWT),
│                          pagination.py, filters.py, razorpay_client.py, send_mail.py
├── tasks.py               Celery task: async confirmation email
├── constants/             messages.py — user-facing response strings, one source of truth
├── management/commands/   send_order_confirmations — idempotent safety-net for missed webhooks,
│                          run manually or wired to Celery Beat later if a real schedule is needed
└── tests/                 auth, products (filter + pagination), orders (stock + concurrency-relevant checks),
                            payments (signature verification, idempotency, unknown order)
```

---

## Running tests
```bash
docker-compose exec web python manage.py test
```

## API screenshots

Live Swagger and API response screenshots are available in [`docs/screenshots/`](docs/screenshots/):

- `swagger-overview.png` - complete endpoint catalogue
- `auth-register.png` - register request and response
- `auth-login.png` - login request and JWT response
- `products-list-complete.png` - products request, headers, and response body
- `orders-create.png` - create-order request and response
- `orders-list.png` - authenticated order-list response
- `orders-detail.png` - authenticated order-detail response
- `payment-create.png` - payment request and Razorpay configuration response
- `webhook-response.png` - webhook request, signature header, and response

31 tests covering: registration, login, product search + pagination meta, order creation (success,
insufficient stock, duplicate product in one request, missing/malformed auth header), order list scoping
(including staff seeing all orders), payment initiation guard clauses (already-paid order, zero-amount
order, existing successful payment), the full failed-then-retried-payment flow end to end, and the
webhook (valid signature, invalid signature, duplicate delivery, unknown order, `payment.captured` vs
`payment.failed` event handling, unhandled event types, amount/currency mismatch, malformed/incomplete
JSON body). Plus a Celery task test confirming email failures actually trigger a retry rather than being
swallowed silently.

---

## What's intentionally out of scope
This project stops short of: a payment ledger / double-entry accounting, a refund state machine, a generic
client-facing idempotency-key system, role-based authorization (admin/merchant roles), CI/CD, and a
reconciliation engine. Those are real backend concepts worth learning, but they describe a fintech-platform
scale of system this project isn't — adding them here would make the project harder to defend in an interview,
not easier.
