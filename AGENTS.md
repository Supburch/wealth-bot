# AGENTS.md — Wealth Bot

You are an AI coding assistant for **Wealth Bot**: a personal investment portfolio LINE bot backed by Google Sheets.

Rules in this file are the project-wide source of truth for Antigravity (and can be shared with other tools).

---

## Project Overview

- Goal: LINE bot to view a personal investment portfolio for 1–10 users.
- Data source: Google Sheets as **read-only** (no buying/selling, no modifying portfolio data via the bot).
- Architecture: LINE Messaging API → FastAPI → Custom Async Cache → Google Sheets API
- Stage: MVP Phase 1 complete; local testing with `uvicorn main:app --reload` and webhook via ngrok.

---

## Tech Stack

- Python 3.12
- FastAPI + Uvicorn
- Pydantic v2 + pydantic-settings
- line-bot-sdk (LINE Messaging API)
- Google Sheets API (gspread, google-auth)
- asyncio for concurrency + custom cache

When suggesting changes:
- Prefer minimal diffs
- Do not introduce new frameworks unless explicitly required

---

## Directory Structure

```
wealthbot/
├── main.py                 # FastAPI app, webhook, health check, lifespan
├── config.py               # Env vars (.env), ALLOWED_USERS and ADMIN_USERS whitelist
├── requirements.txt
├── models/
│   ├── portfolio.py        # DTOs (PortfolioSummary, WealthSummary, HoldingBreakdown, etc.)
│   └── health.py           # DTO for Health Check
├── services/
│   ├── cache.py            # Custom Async Cache (per-key asyncio.Lock, O(1) lookup)
│   ├── sheets_service.py   # Google Sheets client + connection invalidation
│   ├── portfolio_service.py# Business logic and data fetch
│   └── line_service.py     # Map commands and create reply messages
└── tests/
    ├── test_cache.py
    ├── test_portfolio_service.py
    └── test_line_commands.py
```

Placement rules:
- DTOs/schemas → `models/`
- Business logic → `services/`
- Webhook/HTTP/lifespan → `main.py`
- Env/env parsing/whitelist → `config.py` (avoid scattering env reads)

---

## Security & Access Control (Critical)

- Enforce whitelist:
  - `ALLOWED_USERS` must be checked immediately at startup and before responding.
  - `ADMIN_USERS` must be required for admin commands only.
- Never allow operations that mutate data:
  - No writing/updating/deleting Google Sheets from bot commands.
- Never expose or hardcode secrets:
  - `.env` content
  - `GOOGLE_CREDENTIALS_JSON`
  - LINE tokens/secrets
  - User IDs in source code (use env/config)
- Error handling:
  - If a user is not allowed, respond with a generic message (avoid leaking internal details).
  - Catch external API failures (Sheets/LINE) and provide a user-friendly Thai error message.

---

## Cache & Performance Rules

- Use `services/cache.py` for repeated reads.
- Preserve stampede protection:
  - per-key `asyncio.Lock`
  - O(1) lookup through cached dicts for symbol search (e.g. `AAPL`)
- Admin command semantics:
  - `refresh`: clear memory cache only
  - `reload`: clear cache AND recreate the Sheets connection
- Avoid blocking the event loop:
  - Do not introduce synchronous blocking I/O in request handling.

---

## Commands (expected behavior)

### User Commands

| Command | Purpose |
|---------|---------|
| `พอร์ต` | Portfolio value, cost, profit |
| `สรุป` | Summary (top holdings + cash) |
| `วันนี้` | Today's profit |
| `สัดส่วน` | Asset allocation |
| `ถืออะไร`, `top` | Top holdings |
| `เงินสด` | Available cash |
| `winners`, `losers` | Best/worst performers |
| `[Symbol]` e.g. `AAPL` | Holding lookup (O(1) cached dict) |
| `help`, `ช่วยเหลือ` | Help text |

### Utility Commands

| Command | Purpose |
|---------|---------|
| `ping` | Liveness check |
| `version` | Bot version |

### Admin Commands (ADMIN_USERS only)

| Command | Purpose |
|---------|---------|
| `refresh` | Clear memory cache |
| `reload` | Clear cache + recreate Sheets connection |
| `status` | Health check, cache entries, uptime |

When adding or changing commands:
- Update `services/line_service.py`
- Add/adjust unit tests in `tests/test_line_commands.py`

---

## Google Sheets Requirements

- Sheets are the single source of truth.
- Bot must only read from these sheets:
  - `PortfolioSummary`
  - `TodaySummary`
  - `AssetAllocation`
  - `HoldingsBreakdown`
- The Sheets service must support connection invalidation for `reload`.

---

## Development Commands

```bash
pip install -r requirements.txt
uvicorn main:app --reload
pytest
pytest tests/test_cache.py -v
pytest tests/test_portfolio_service.py -v
pytest tests/test_line_commands.py -v
curl http://localhost:8000/health
```

Local webhook: expose via ngrok and point LINE Developers Console to the webhook URL.

---

## Testing Requirements

- Add tests for every new command/service behavior.
- Mock Google Sheets and LINE API in unit tests.
- Cover at least:
  - cache stampede protection
  - whitelist rejection
  - admin-only enforcement
  - O(1) symbol lookup path
- Run `pytest` before considering a task complete.

---

## Code Style

- Use type hints on public functions and service methods.
- Use Pydantic v2 models for DTOs; avoid raw dicts at service boundaries.
- Prefer small, focused functions; split files before ~300 lines.
- Use async/await consistently in FastAPI routes and services.
- User-facing LINE messages in **Thai**; code, logs, and internal docs in **English**.

---

## Output Expectations

- Explain changes focusing on **why**, not just what.
- List files added/modified and which tests to run.
- For security-related changes, restate the affected rule(s).
- Ask before: new dependencies, Sheets schema changes, or large refactors.

---

## Prohibited / Must Not

- Must not write to Google Sheets from the bot
- Must not bypass whitelist checks
- Must not commit or log secrets
- Must not add endpoints that mutate portfolio data
- Must not introduce event-loop blocking operations
- Must not do large refactors without explicit user approval
