# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

Argus is a RAG (Retrieval-Augmented Generation) knowledge base platform with:
- **Backend**: Python FastAPI + SQLAlchemy async + PostgreSQL/pgvector
- **Frontend**: Vue 3 + TypeScript + Vite + Element Plus
- **Infrastructure**: Docker Compose (PostgreSQL, MinIO, Elasticsearch)

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

## Architecture

```
Argus-python/app/
├── main.py                        # FastAPI entry, lifespan, CORS, routers
├── config.py                      # Pydantic Settings (env_file=.env)
├── dependencies.py                # Async engine + session factory
├── database.py                    # SQLAlchemy Base
├── common/                        # Shared: ApiResponse, exceptions, middleware
├── auth/                          # JWT auth, login/register/refresh, password hashing
├── user/                          # Account settings, admin user CRUD
├── group/                         # Group CRUD, memberships, invitations, join requests
├── document/                      # Upload (direct + chunked), list, preview, download, delete
├── ingestion/                     # ETL pipeline: parse → clean → chunk → vectorize → ES index
├── qa/                            # RAG QA: query planning → hybrid retrieval → LLM generation
│   ├── query_planning.py          #   DIRECT/REWRITE/DECOMPOSE strategy via LLM
│   ├── retrieval.py               #   Vector + ES hybrid, RRF fusion, evidence assessment
│   └── service.py                 #   QA orchestration, streaming SSE
├── assistant/                     # AI Agent: ReactAgent + tool calling + session memory
│   ├── agent/                     #   LangGraph agent factory, KB search tool
│   └── memory/                    #   Short-term memory manager
├── metrics/                       # LLM usage tracking and statistics
├── models_config/                 # Admin model config management (chat + embedding)
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

### API Response
- Every controller returns `ApiResponse` — `success`, `data`, `message`
- Throw `BusinessException`(400) / `ForbiddenException`(403) / `AuthenticationException`(401)
- Snake_case in Python dicts → camelCase via frontend Axios interceptor

### Auth Flow
- JWT Bearer token in `Authorization` header → `JwtAuthenticationFilter` dependency
- `get_current_user` → returns `AuthenticatedUser` record
- `require_admin` → admin-only routes
- Refresh token stored as httpOnly cookie (`path=/api`, `SameSite=Lax`)
- Access token persisted in `localStorage` (argus_access_token) for page refresh survival
- Account switcher saves up to 5 accounts in localStorage (argus_accounts)

### Streaming QA
- Backend: `POST /api/qa/stream-ask` → SSE events: `answer` (JSON-encoded), `citations`, `done`
- Frontend: `streamAskQuestion()` in `qa.ts` → `QaStreamHandlers` (onToken, onAnswer, onCitations)
- Answer text JSON-wrapped to prevent SSE newline breakage
- LLM response uses delimiter format (`<<<ANSWER>>>`/`<<<THINKING>>>`/`<<<CITATIONS>>>`)

### Time Handling
- All DB timestamps are naive UTC (via `utcnow()` helper in `app/common/time_utils.py`)
- ISO format `+ "Z"` suffix on serialization to ensure correct browser parsing

## Configuration

- **.env file**: `Argus-python/.env` (copy from `.env.example`)
- **Active models**: Admins can override via System Settings → Add Model (stored in `model_configs` table, falls back to `.env`)
- **Default admin**: admin@argus.local / Admin@123456 (seeded by `init_db.py` or `_seed_dev_admin()`)
- **Vite proxy**: `/api` → `http://localhost:10001` (configured in `vite.config.ts`)
