# AGENTS.md — Wealth Bot

You are an AI coding assistant for **Wealth Bot**: a personal investment portfolio LINE bot backed by Google Sheets.

Rules in this file are the project-wide source of truth for Antigravity (and can be shared with other tools).

---

## Project Overview

- Goal: LINE bot to view a personal investment portfolio for 1–10 users.
- Data source: Google Sheets as **read-only** (no buying/selling, no modifying portfolio data via the bot).
- Stage: MVP Phase 1 complete; refactoring toward layered architecture (handlers, repository pattern).

---

## Architecture

```
LINE Messaging API
       │
       ▼
  FastAPI (main.py)
  /callback  /health
       │
       ▼
  line_service.py          ← main dispatcher (monolithic if/elif)
       │
  ┌────┴────────────┐
  │                 │
  ▼                 ▼
portfolio_service   user_mapping_service
  │                 │
  ▼                 ▼
portfolio_repository   sheets_service (Master Sheet)
  │
  ▼
sheets_service (Google Sheets API / gspread)
```

### Layer Responsibilities

| Layer | File | Role |
|-------|------|------|
| **Entry** | `main.py` | FastAPI app, `/callback` webhook, `/health`, lifespan |
| **Dispatcher** | `services/line_service.py` | Route LINE text commands (monolithic if/elif); format Thai replies |
| **Router (new)** | `services/command_router.py` | Command → handler mapping (refactoring target) |
| **Handlers (new)** | `handlers/*.py` | One handler per command; returns `AppResponse` |
| **Business Logic** | `services/portfolio_service.py` | Parse portfolio data, compute summaries |
| **User Auth** | `services/user_mapping_service.py` | Map LINE user ID → spreadsheet via Master Sheet |
| **Data Access** | `repositories/portfolio_repository.py` | Read raw rows from per-user spreadsheet |
| **Infrastructure** | `services/sheets_service.py` | gspread client, Master Sheet + per-user sheets |
| **Cache** | `services/cache.py` | Async cache with per-key lock (stampede protection) |
| **Presentation** | `builders/*.py` | Build Flex messages and formatted text |

### Data Flow

1. LINE sends text → `main.py` `/callback`
2. `line_service.handle_user_command(user_id, text)` is called
3. `user_mapping_service.get_user(user_id)` reads **Master Sheet** (`Users` tab) → returns `UserInfo` (spreadsheet_id, role, enabled)
4. Portfolio commands call `portfolio_service` → `portfolio_repository` → `sheets_service` using **per-user spreadsheet_id**
5. Reply formatted in Thai and sent back via LINE Messaging API

### Google Sheets Layout

**Master Spreadsheet** (`MASTER_SPREADSHEET_ID`):
- Tab `Users`: columns `LINE_USER_ID`, `SPREADSHEET_ID`, `ROLE`, `ENABLED`

**Per-User Spreadsheet** (one per user):
- `PortfolioSummary`
- `TodaySummary`
- `AssetAllocation`
- `HoldingsBreakdown`

---

## Tech Stack

- Python 3.12
- FastAPI + Uvicorn
- Pydantic v2 + pydantic-settings
- line-bot-sdk v3 (LINE Messaging API)
- Google Sheets API (gspread, google-auth)
- asyncio + custom async cache

When suggesting changes:
- Prefer minimal diffs
- Follow existing layer boundaries (do not skip repository to call sheets directly from handlers)
- Do not introduce new frameworks unless explicitly required

---

## Directory Structure

```
wealthbot/
├── main.py                      # FastAPI app, /callback, /health, lifespan
├── config.py                    # Env vars (.env), legacy settings
├── requirements.txt
├── AGENTS.md                    # This file
├── CLAUDE.md                    # @AGENTS.md bridge for Claude Code
├── core/
│   ├── config.py                # AppConfig (new)
│   ├── constants.py
│   ├── enums.py                 # ResponseType, etc.
│   ├── exceptions.py            # PortfolioReadError, PortfolioParseError
│   └── messages.py              # Thai/English message constants
├── models/
│   ├── portfolio.py             # DTOs: PortfolioSummary, WealthSummary, HoldingBreakdown
│   ├── health.py                # HealthDto
│   ├── user.py                  # UserInfo
│   └── response.py              # AppResponse (text / rich)
├── repositories/
│   └── portfolio_repository.py  # Raw row fetch from Sheets
├── services/
│   ├── cache.py                 # Async cache (per-key asyncio.Lock, O(1) lookup)
│   ├── sheets_service.py        # gspread client + Master Sheet + per-user sheets
│   ├── portfolio_service.py     # Business logic + parsing
│   ├── user_mapping_service.py  # LINE user → spreadsheet mapping
│   ├── line_service.py          # Main dispatcher (monolithic if/elif) — current entry
│   └── command_router.py        # Handler-based routing — refactoring target
├── handlers/
│   ├── base.py                  # CommandHandler protocol
│   ├── portfolio_handler.py
│   └── help_handler.py
├── builders/
│   ├── portfolio_flex_builder.py
│   └── help_text_builder.py
└── tests/
    ├── test_cache.py
    ├── test_portfolio_service.py
    └── test_line_commands.py
```

### Placement Rules

- DTOs/schemas → `models/`
- Business logic → `services/`
- Raw data fetch → `repositories/`
- Command handling → `handlers/` (new) or `line_service.py` (legacy)
- Message formatting → `builders/` or inline in `line_service.py`
- Shared constants/exceptions → `core/`
- Webhook/HTTP → `main.py`
- Env/config → `config.py` / `core/config.py`

---

## Security & Access Control (Critical)

- User access is controlled via **Master Sheet** (`Users` tab), not hardcoded env whitelist.
- `user_mapping_service.get_user()` must be called before processing any command.
- Reject disabled or unknown users with a generic message.
- Admin commands (`refresh`, `reload`, `status`) require `user_info.is_admin` (ROLE = admin).
- Never write/update/delete Google Sheets from bot commands.
- Never commit or log secrets: `.env`, `GOOGLE_CREDENTIALS_JSON`, LINE tokens, service account JSON files.

---

## Cache & Performance Rules

- Use `services/cache.py` for repeated reads (user mappings, portfolio data).
- Preserve stampede protection: per-key `asyncio.Lock`.
- O(1) symbol lookup via cached dict for holding search (e.g. `AAPL`).
- Admin command semantics:
  - `refresh`: clear memory cache only
  - `reload`: clear cache AND invalidate gspread client (`invalidate_client()`)
- Avoid blocking the event loop with synchronous gspread calls in hot paths.

---

## Commands

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

Prefix `หุ้น ` is stripped before routing (e.g. `หุ้น AAPL` → `AAPL`).

### Utility Commands

| Command | Purpose |
|---------|---------|
| `ping` | Liveness check |
| `version` | Bot version |

### Admin Commands (admin role only)

| Command | Purpose |
|---------|---------|
| `refresh` | Clear memory cache |
| `reload` | Clear cache + recreate Sheets connection |
| `status` | Health, cache entries, uptime |

When adding commands:
- Legacy path: update `services/line_service.py`
- New path: add handler in `handlers/`, register in `command_router.py`
- Add tests in `tests/test_line_commands.py`

---

## Refactoring Notes

The project is transitioning from monolithic `line_service.py` to handler-based architecture:

| Current (production) | Target (refactoring) |
|---------------------|----------------------|
| `line_service.py` if/elif | `command_router.py` + `handlers/` |
| Function-based portfolio_service | Class-based `PortfolioService` + `PortfolioRepository` |
| Inline text replies | `builders/` + `AppResponse` (text / Flex) |

When implementing new features, prefer the **handler + repository** pattern unless explicitly told to use the legacy path.

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

Local webhook: expose via ngrok → point LINE Developers Console to `/callback`.

### Key Environment Variables

- `GOOGLE_CREDENTIALS_JSON` — service account credentials (JSON string)
- `MASTER_SPREADSHEET_ID` — Master Sheet for user mapping
- `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_CHANNEL_SECRET`
- Per-user `SPREADSHEET_ID` is stored in Master Sheet, not in `.env`

---

## Testing Requirements

- Mock Google Sheets and LINE API in unit tests.
- Cover: cache stampede, unauthorized user rejection, admin-only enforcement, O(1) symbol lookup.
- Run `pytest` before considering a task complete.

---

## Code Style

- Type hints on public functions and service methods.
- Pydantic v2 models for DTOs; avoid raw dicts at service boundaries.
- Small, focused functions; split files before ~300 lines.
- User-facing LINE messages in **Thai**; code, logs, and internal docs in **English**.

---

## Output Expectations

- Explain changes focusing on **why**, not just what.
- List files added/modified and which tests to run.
- Respect layer boundaries — do not call `sheets_service` directly from handlers; go through service/repository.
- Ask before: new dependencies, Master Sheet schema changes, or large refactors.

---

## Prohibited / Must Not

- Write to Google Sheets from the bot
- Bypass user mapping / enabled check
- Commit or log secrets
- Add endpoints that mutate portfolio data
- Skip repository layer to access Sheets directly from handlers
- Large refactors without explicit user approval
