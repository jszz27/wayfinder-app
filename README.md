# Wayfinder

AI-powered communication and digital accessibility platform.
Full product plan and specification: [`Plan.md`](./Plan.md).

> **Status: Sprint 1 — WebSocket caption MVP.**
> A minimal working path from microphone input, through the WebSocket
> server, to STT, to captions rendered in the widget. Guide mode, auth,
> persistence, and CI/CD are later sprints (see `Plan.md` §12).

## Repository layout

| Path | `Plan.md` §3 component | Sprint 1 status |
|---|---|---|
| `frontend/` | Lightweight React widget | Implemented |
| `backend-ws/` | WebSocket server (caption streaming) | Implemented |
| `backend-rest/` | REST API server (FastAPI) | Skeleton — health + session creation |
| `backend-ws/app/stt/` | External AI API (STT) | STT only; no TTS or LLM yet |
| — | PostgreSQL | Sprint 3 |
| — | GitHub Actions / Cloud Run | Sprint 4 (`Dockerfile`s staged now) |

Documentation is written in English to match `Plan.md`; the widget's
user-facing strings are Korean, matching the default `STT_LANGUAGE=ko-KR`.

## Running locally

Requires Python 3.12+ and Node 20+. Copy `.env.example` to `.env` first.

```powershell
# terminal 1 — REST API server
cd backend-rest; uvicorn app.main:app --port 8000 --reload

# terminal 2 — WebSocket caption server
cd backend-ws;   uvicorn app.main:app --port 8001 --reload

# terminal 3 — widget
cd frontend;     npm run dev      # http://localhost:5173
```

With `WAYFINDER_STT=mock` the full path runs without any cloud
credentials. Set `WAYFINDER_STT=google` plus the `GOOGLE_*` variables to
use real Google Cloud Speech-to-Text v2 streaming.

## Tests

```powershell
cd backend-ws;   pytest
cd backend-rest; pytest
cd frontend;     npm run build    # type-check + bundle
```

## Sprint log

Per `Plan.md` §12, each sprint closes with a short retrospective here.

### Sprint 1 (weeks 1–2) — WebSocket caption MVP
Issue checklist: [`docs/sprint-1.md`](./docs/sprint-1.md). Retrospective
to be written at sprint review.
