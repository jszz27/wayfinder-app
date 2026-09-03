# Wayfinder

AI-powered communication and digital accessibility platform.
Full product plan and specification: [`Plan.md`](./Plan.md).

> **Status: Sprint 1 complete — WebSocket caption MVP.**
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
Issue checklist and verification evidence:
[`docs/sprint-1.md`](./docs/sprint-1.md).

**Delivered.** The whole intended path runs: microphone → WebSocket → STT
→ captions on screen. 26 tests pass (18 in `backend-ws`, 8 in
`backend-rest`) and the widget builds clean. Every acceptance criterion is
met except live transcription against Google.

**What worked.** Settling the two ambiguities in `Plan.md` §5 *before*
writing code — what `caption.seq` counts, and the exact audio wire format
— and recording both in `docs/sprint-1.md` rather than in code comments.
Each had two plausible readings, and picking one silently would have meant
a client and a server that disagreed at integration time.

Building the mock STT adapter first was the other decision that paid off.
It let the full path be assembled and verified end to end with no cloud
account, so the sprint was never blocked waiting on credentials, and the
`SttStream` seam it forced is what makes the Google adapter a drop-in.

**What did not.** The `google` extra was never installed until sprint
close, so the Google adapter sat unparsed against the real SDK for the
whole sprint — written, plausible, and completely unverified. Installing
it took under a minute and would have caught any wrong type or renamed
field immediately. *Install the dependency when you write the adapter,
even when you cannot yet call the service.*

The related miss: the credential dependency was known from day one but
never raised as a blocker until the checklist was being closed out. It
should have been flagged at sprint planning, when there was still time to
request access.

**What live testing caught that mocks could not.** The mock adapter emits
caption lines of a fixed length. Real speech does not, and a long sentence
made the whole widget jump sideways several times a second — a layout bug
that had been latent since Issue 0 and that no test, and no amount of
mock-driven clicking, would ever have surfaced. Worth remembering when a
sprint leans on a stand-in for the one dependency it cannot reach:
*variability is part of the behaviour being stubbed out.*

**Carried into Sprint 2.** Nothing from Sprint 1 — all acceptance criteria
are met. Sprint 2 starts on guide mode (`Plan.md` §10).
