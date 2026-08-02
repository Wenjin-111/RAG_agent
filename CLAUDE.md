# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

Argus is a RAG (Retrieval-Augmented Generation) knowledge base platform with:
- **Backend**: Python FastAPI + SQLAlchemy async + PostgreSQL/pgvector
- **Frontend**: Vue 3 + TypeScript + Vite + Element Plus
- **Infrastructure**: Docker Compose (PostgreSQL, MinIO, Elasticsearch)
- **Admin console**: platform-wide document/group/QA-history management, insights, system health, audit logs

## Build Commands

```bash
# Backend (Python)
cd Argus-python
pip install -r requirements.txt
python init_db.py              # Initialize DB tables + seed admin
uvicorn app.main:app --host 0.0.0.0 --port 10001 --reload

# Frontend (Vue 3)
cd Argus-frontend
npm install
npm run dev                    # Dev server on http://localhost:5173

# Infrastructure
docker compose up -d           # Start PG + MinIO + ES
docker compose ps              # Check health
docker compose down            # Stop (data preserved in volumes)
```

## Tech Stack

- **Python 3.12+** with FastAPI, SQLAlchemy 2.0 async, asyncpg
- **Vue 3.5** (Composition API, `<script setup>`), TypeScript, Vite 8
- **PostgreSQL 16 + pgvector** — HNSW vector index, cosine distance
- **Elasticsearch 8.x** — BM25 keyword search, IK Chinese tokenizer
- **MinIO** — S3-compatible object storage for documents
- **LangChain / LangGraph** — AI agent framework (ReactAgent + MemorySaver)
- **Pydantic v2** — Settings and request validation
- **JWT** (PyJWT) — Access token auth
- **Passlib + bcrypt** — Password hashing
- **Axios** — Frontend HTTP client (with snake_case→camelCase interceptor)
- **KaTeX + DOMPurify** — Markdown/LaTeX rendering (frontend, unified in `utils/markdown.ts`)

## Architecture

```
Argus-python/app/
├── main.py                        # FastAPI entry, lifespan, routers, periodic cleanup task
├── config.py                      # Pydantic Settings (env_file=.env)
├── dependencies.py                # Async engine + session factory
├── database.py                    # SQLAlchemy Base
├── common/                        # Shared: ApiResponse, exceptions, middleware, UserContext
├── auth/                          # JWT auth, login/register/refresh, password hashing
├── user/                          # Account settings, admin user CRUD + create user
├── group/                         # Group CRUD, memberships, invitations, join requests + admin router
├── document/                      # Upload (direct + chunked), list, preview, download, delete + admin router
│   └── maintenance.py             # Expired upload-session cleanup (hourly)
├── ingestion/                     # ETL pipeline: parse → clean → chunk → vectorize → ES index
├── qa/                            # RAG QA: query planning → hybrid retrieval → LLM generation
│   ├── models.py                  #   QaSession / QaMessage (persisted, with evidence_level)
│   ├── history_service.py         #   QA history queries (user + admin views)
│   ├── retrieval.py               #   Parallel vector+ES, RRF fusion, evidence assessment
│   └── service.py                 #   QA orchestration, streaming SSE, persistence
├── assistant/                     # AI Agent: ReactAgent + tool calling + session memory
│   ├── agent/                     #   LangGraph agent factory, KB search tool
│   └── memory/                    #   Short-term memory manager (LLM semantic summary)
├── metrics/                       # LLM usage tracking, stats, platform insights
├── models_config/                 # Admin model config management (chat + embedding)
├── audit/                         # Audit trail (sensitive operations) + admin router
├── system/                        # System health check endpoint
└── engine/                        # Infrastructure adapters
    ├── vector_store.py            #   PGvector adapter (custom SQL, LangChain-free)
    ├── es_service.py              #   Elasticsearch index + search
    └── storage.py                 #   MinIO client
```

## Key Conventions

### Database
- All DB access via SQLAlchemy 2.0 async (`select()`, `update()`, `delete()`)
- Use `async_session_factory` from `dependencies.py` for manual sessions
- Route handlers get sessions via `Depends(get_db)` (auto-commit on success, rollback on exception)
- Models use `Mapped[]` type annotations, extend `Base` from `database.py`
- New tables auto-created on startup (`Base.metadata.create_all`); one-off column additions
  use idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `main.py:_init_database`

### API Response
- Every controller returns `ApiResponse` — `success`, `data`, `message`
- Throw `BusinessException`(400) / `ForbiddenException`(403) / `AuthenticationException`(401)
- Snake_case in Python dicts → camelCase via frontend Axios interceptor
- **Exceptions**: `qa/ask`, `qa/stream-ask` (direct payload), `assistant/sessions` list/detail/context (direct payload)
- **Pagination convention**: admin list endpoints return `{items, total, page, limit}`

### Auth Flow
- JWT Bearer token in `Authorization` header → `JwtAuthenticationFilter` dependency
- `get_current_user` → returns `AuthenticatedUser` record (also sets `UserContext` — read in `LoggingMiddleware` for `userId=` in access logs)
- `require_admin` → admin-only routes
- Refresh token stored as httpOnly cookie (`path=/api`, `SameSite=Lax`)
- Access token persisted in `localStorage` (argus_access_token) for page refresh survival
- Account switcher saves up to 5 accounts in localStorage (argus_accounts)

### Authorization
- `require_group_access(db, user_id, system_role, group_id)` (group/service.py) — admins bypass; members of ACTIVE groups pass; DISABLED/DELETED groups → 403
- Document-scoped endpoints resolve the document's own group for access checks (`_check_document_access`) — never trust a client-supplied groupId for document lookup
- Upload sessions verify owner (`uploader_user_id`) on chunk/complete/status

### Streaming QA
- Backend: `POST /api/qa/stream-ask` → SSE events: `token` (streamed deltas), `answer`, `citations` (with optional `reasonCode`/`reasonMessage` on refusal), `done`
- `sessionId` in request body appends the round to an existing QA session (cloud history continuation)
- No-evidence (NONE) short-circuits before the LLM call
- LLM response uses delimiter format (`<<<ANSWER>>>`/`<<<THINKING>>>`/`<<<CITATIONS>>>`); `StreamingAnswerParser` streams only the answer section

### QA Persistence (cloud history)
- Every Q&A round is persisted to `qa_sessions`/`qa_messages` (non-critical, failures swallowed)
- `qa_messages.evidence_level` records SUFFICIENT/PARTIAL/WEAK/NONE for retrieval-quality insights
- User-facing endpoints: `GET/DELETE /api/qa/sessions`, `GET /api/qa/sessions/{id}` (ownership-checked)
- Admin endpoints: `/api/admin/qa/sessions` (list/detail, any user)

### Assistant
- Memory: `maintain_before_response(session_id, user_id)` compacts when >20 msgs or >8000 chars — LLM semantic summary into `summary_text` (fallback: concatenation)
- Pagination: `GET /api/assistant/sessions/{id}/messages?beforeId=&limit=` returns `{items, hasMore, nextBeforeId}` (ascending order)
- Archive: status ACTIVE/ARCHIVED/DELETED; `POST .../archive`, `.../restore`; `GET /api/assistant/sessions?status=`; lazy auto-archive after 30 idle days (`ARCHIVE_IDLE_DAYS`)
- LLM usage recorded (estimated tokens) in `llm_usage_records` (module=assistant)

### Audit
- `AuditService.log()` / helper `log_audit(db, user, action, target_type, target_id, detail)` — call after sensitive operations (doc delete/retry, group ban/dissolve/member-remove, user create/status/reset, model config changes)
- Actions are UPPER_SNAKE strings; view at `/api/admin/audit-logs`

### Time Handling
- All DB timestamps are naive UTC (via `utcnow()` helper in `app/common/time_utils.py`)
- ISO format `+ "Z"` suffix on serialization (all `_fmt` helpers) to ensure correct browser parsing

### Configuration
- **.env file**: `Argus-python/.env` (copy from `.env.example` — placeholder keys only)
- **Active models**: Admins can override via System Settings → Add Model (stored in `model_configs` table, falls back to `.env`); query planning, QA generation, auto-title and memory summaries all resolve via `get_chat_config(user_id)`
- **Default admin**: admin@argus.local / Admin@123456 (seeded by `init_db.py` or `_seed_dev_admin()`)
- **Vite proxy**: `/api` → `http://localhost:10001` (configured in `vite.config.ts`)

### Docs
- `docs/代码审查修复报告.md` — review findings and fix log (keep updated when fixing issues)
- `TODO.md` — pending feature plans (e.g. agent tool expansion)
