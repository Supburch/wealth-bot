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
  command_router.py        ← main dispatcher (handler-based routing)
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
| **Dispatcher** | `services/command_router.py` | Route LINE text commands (handler-based); format Thai replies |
| **Handlers (new)** | `handlers/*.py` | One handler per command; returns `AppResponse` |
| **Business Logic** | `services/portfolio_service.py` | Parse portfolio data, compute summaries |
| **User Auth** | `services/user_mapping_service.py` | Map LINE user ID → spreadsheet via Master Sheet |
| **Data Access** | `repositories/portfolio_repository.py` | Read raw rows from per-user spreadsheet |
| **Infrastructure** | `services/sheets_service.py` | gspread client, Master Sheet + per-user sheets |
| **Cache** | `services/cache.py` | Async cache with per-key lock (stampede protection) |
| **Presentation** | `builders/*.py` | Build Flex messages and formatted text |

### Data Flow

1. LINE sends text → `main.py` `/callback`
2. `command_router.route_command(user_id, text)` is called
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
│   └── command_router.py        # Handler-based routing
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
    └── test_handlers.py
```

### Placement Rules

- DTOs/schemas → `models/`
- Business logic → `services/`
- Raw data fetch → `repositories/`
- Command handling → `handlers/`
- Message formatting → `builders/`
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
- Add handler in `handlers/`, register in `command_router.py`
- Add tests in `tests/test_handlers.py`

---

## Refactoring Notes

The project uses a handler-based architecture (the legacy `line_service.py` dispatcher was removed in P1):

| Concern | Pattern |
|---------|---------|
| Command dispatch | `command_router.py` + `handlers/` |
| Business logic | `PortfolioService` + `PortfolioRepository` |
| Reply formatting | `builders/` + `AppResponse` (text / Flex) |

When implementing new features, use the **handler + repository** pattern.

---

## Known Gaps (Documented, Non-Blocking)

Error handling read paths have inconsistent shapes:

- `repositories/portfolio_repository.py` → typed `PortfolioReadError` (clean).
- `services/user_mapping_service.py` and the module-level `@cached` portfolio functions → raw exception (untyped).
- After **P2.4a**, `PortfolioHandler`, `PortfolioService.get_portfolio`, and `ValidationService.validate_portfolio` no longer swallow unexpected exceptions with a broad `except Exception`; they catch only the typed domain errors (`PortfolioReadError`, `PortfolioParseError`) and let anything else bubble up.

**Impact:** the two raw boundaries above can still raise untyped exceptions. As of **P2.4c**, `CommandRouter.route_command` has a centralized catch-all that logs the traceback and returns `UNEXPECTED_ERROR`, so these no longer crash the webhook — but they still aren't surfaced as typed domain errors until the boundaries are wrapped.

**Remaining fix (Deferred — not yet scheduled):** introduce a shared `SheetsReadError`, `raise … from e` at the two raw boundaries, and relabel the misleading log messages. Does not touch cache/retry/lock logic.

**`reply_message` guarded (resolved):** `main.py`'s `line_bot_api.reply_message(...)` call is now wrapped in try/except; an SDK/network failure is logged via `logger.exception` (request_id-correlated, no PII) and the webhook still returns HTTP 200 so LINE does not retry. Covered by `tests/test_webhook.py::test_callback_reply_message_failure_returns_200`.

**Duplicate detection decoupled from numeric validity (resolved):** `validation_service.py` now registers every row's raw non-empty symbol into the duplicate map during the per-row loop, independent of numeric parsing, so a symbol on both a clean row and a row with a numeric parse error is still flagged. Empty/whitespace symbols stay excluded from duplicate comparison (they are only flagged "Symbol is empty"). Covered by `tests/test_validation.py`.

**`wealth_summary_handler.py` is entirely English (Deferred — not yet scheduled):** The handler constructs its summary in English (`Portfolio Value:`, `Top Holdings:`), which is inconsistent with the rest of the bot's Thai UI guidelines. The new best/worst headline deliberately matches this existing English convention for local consistency until a full i18n pass is scheduled.

---

## Development Commands

```bash
pip install -r requirements.txt
uvicorn main:app --reload
pytest
pytest tests/test_cache.py -v
pytest tests/test_portfolio_service.py -v
pytest tests/test_handlers.py -v
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

---

## Progress Log

### 2026-08-19 — P2.4a: remove broad `except Exception` from read paths

- `handlers/portfolio_handler.py`: dropped `except Exception` → `UNEXPECTED_ERROR`; `handle` now catches only `PortfolioReadError` / `PortfolioParseError`, everything else bubbles up.
- `services/portfolio_service.py`: dropped `except Exception` → `ServiceResult(error="Internal service error")` in `get_portfolio`; domain errors still map to `ServiceResult`.
- `services/validation_service.py`: dropped the synthetic `ValidationIssue` fallback on unexpected exceptions.
- Added 4 regression tests (bubbles-up behavior for the three layers + `PortfolioReadError` → `PORTFOLIO_READ_ERROR` mapping).
- Tests: **140 passed, 2 skipped** (full suite, `tests/test_webhook.py` included: 4 passed).

### 2026-08-20 — P2.4c: centralized catch-all in CommandRouter

- `services/command_router.py`: `route_command` now wraps handler/symbol dispatch in a single `except Exception` catch-all — the one intentional broad catch in the request path. It logs the full traceback via `logger.exception` and returns the existing `UNEXPECTED_ERROR` message instead of letting unexpected exceptions crash the webhook.
- Complements P2.4a (which removed broad catches from the read/validation layers) and unblocks P2.4b.
- Added `tests/test_command_router.py` with 4 tests: normal path, unknown command, handler exception → `UNEXPECTED_ERROR`, symbol fallback exception → `UNEXPECTED_ERROR`.
- Tests: **144 passed, 2 skipped** (full suite).

### 2026-08-20 — P2.4b: remove broad `except Exception` from handlers

- Removed the identical broad `except Exception → UNEXPECTED_ERROR` block from 9 handlers (`admin_handler`, `allocation_handler`, `help_handler`, `holdings_handler`, `symbol_handler`, `today_handler`, `utility_handler`, `validate_handler`, `wealth_summary_handler`); unexpected exceptions now bubble up to `CommandRouter.route_command`'s P2.4c catch-all.
- Dropped the now-unused `import logging` / `logger` declarations and `UNEXPECTED_ERROR` imports (kept `UNEXPECTED_ERROR` in `admin_handler`, which still uses it for the unknown-command fallback).
- Updated 2 tests to assert bubbles-up instead of `UNEXPECTED_ERROR`: `test_validation.py::test_validate_handler_writeback_failure_bubbles_up` and `test_user_mapping_service.py::test_handler_bubbles_up_on_fetch_failure`.
- Tests: **144 passed, 2 skipped** (full suite).
