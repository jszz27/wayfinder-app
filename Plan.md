# Wayfinder — AI-Powered Communication & Digital Accessibility Platform — Full Plan

## 1. Project Overview

**Wayfinder** is a web-based accessibility tool for two user groups: people who struggle to follow real-time conversations (deaf/hard-of-hearing students, international students still learning the language), and people who struggle with basic digital services because the UI is unfamiliar to them (seniors using banking or delivery apps).

- **Problem**: Both groups face a "barrier to accessing information and communication" that causes everyday friction. Deaf students and international students miss real-time conversations (lectures, meetings, events), while seniors struggle to use basic digital services like banking or delivery apps on their own.
- **Solution**: (1) A live captioning feature that converts speech to text in real time, and (2) a conversational feature where the user describes their situation and an AI explains, in plain language, the next step to take. Both features live in the same platform as separate "modes."
- **Outcome**: The impact can be demonstrated with concrete numbers — reduced communication lag, higher guidance-completion rates — while also producing a portfolio project that covers cloud, REST API, WebSocket, CI/CD, and Agile experience all at once.

## 2. Mapping to the Target Job Requirements

| JD requirement | How this project covers it |
|---|---|
| Cloud services experience | Deployed on GCP Cloud Run |
| REST APIs / databases | REST API server + PostgreSQL |
| CI/CD or automation tools | GitHub Actions for test → build → deploy automation |
| Personal / open-source projects | Designed and built from scratch as a personal project |
| Agile development methods | Two-week sprints managed via GitHub Projects |

## 3. Architecture

```
User (lightweight web widget)
        │
   ┌────┴────┐
   ▼         ▼
REST API   WebSocket server
server     (real-time caption streaming)
   │         │
   ▼         ▼
Database    External AI API
(PostgreSQL) (STT · TTS · LLM)

GitHub Actions → Cloud deployment (GCP Cloud Run) → deploys REST/WebSocket servers
```

- **Frontend**: A lightweight React widget. No page navigation — kept to a start/stop button and a caption text stream window.
- **REST API server (FastAPI)**: Handles request/response work — authentication, session management, the senior guide mode (LLM conversation).
- **WebSocket server**: Streams microphone or tab audio in real time to an STT API and returns partial/final caption text immediately. Chosen over REST because latency matters here.
- **Database (PostgreSQL)**: Stores users, caption session/log data, and guide conversation logs.
- **External AI API**: STT (speech-to-text), TTS (text-to-speech), LLM (guide conversation generation).
- **CI/CD (GitHub Actions)**: Automates test, build, and deploy on every push.
- **Cloud deployment (GCP Cloud Run)**: Serverless containers, minimal cost when idle.

## 4. REST API Endpoints

**Authentication**
- `POST /api/auth/signup` — Sign up
- `POST /api/auth/login` — Log in, issue JWT
- `POST /api/auth/refresh` — Refresh access token
- `DELETE /api/auth/logout` — Log out

**Caption sessions (for retrieving logs)**
- `POST /api/caption-sessions` — Start a session. Body includes `audio_source: "mic" | "tab_audio"`
- `GET /api/caption-sessions/{session_id}` — Get a session's caption log
- `GET /api/caption-sessions` — List my sessions
- `DELETE /api/caption-sessions/{session_id}` — Delete a session

**Digital guide mode**
- `POST /api/guide/sessions` — Start a guide session
- `POST /api/guide/sessions/{session_id}/messages` — Send a situation description → get the AI's next-step response. Body includes the text question plus an optional `screenshot: "<base64 image>"` (included only while screen sharing is on)
- `GET /api/guide/sessions/{session_id}` — Get conversation history
- `PATCH /api/guide/sessions/{session_id}/complete` — Mark the session complete

**User settings**
- `GET /api/users/me` — Get profile/settings
- `PATCH /api/users/me` — Update accessibility settings

## 5. WebSocket Message Spec

**Endpoint**: `wss://api.example.com/ws/caption?session_id={session_id}[&language={tag}]`

`language` is the BCP-47 tag the listener has pinned in settings, and is optional. Absent means detect the language, which is what every session did before the setting existed. Present, it pins the recogniser and turns detection off — the setting would be advisory rather than a choice if a detector could still overrule it. A tag that is not well-formed is ignored rather than fatal: a preference should never be the reason captions do not start. Added in Sprint 3 to carry §8's language setting to the recogniser; see `docs/sprint-3.md`.

Client → server:
```json
{ "type": "audio_chunk", "data": "<base64>", "seq": 42, "source": "mic" }
{ "type": "end_stream" }
```
`source` is either `"mic"` (microphone input) or `"tab_audio"` (audio from the shared browser tab), fixed once at the start of the session.

Server → client:
```json
{ "type": "caption", "text": "...", "is_final": false, "seq": 42, "language": "ko-KR" }
{ "type": "error", "message": "..." }
{ "type": "stream_ended", "session_id": "..." }
```

`is_final: false` marks an interim result that may still be revised; `is_final: true` marks a confirmed sentence, and only confirmed sentences are written to the database.

`caption.language` is the BCP-47 tag the audio was recognised as. It is present only when the language was detected rather than configured, and `null` otherwise — so a session with a pinned `language` reports `null` throughout, because there was nothing to work out. Added after Sprint 1; see `docs/sprint-1.md`.

## 6. Database Schema (PostgreSQL)

```
users
  id (PK), email, password_hash, display_name, created_at

caption_sessions
  id (PK), user_id (FK), started_at, ended_at, language, audio_source (mic/tab_audio)

caption_lines
  id (PK), session_id (FK), seq, text, created_at

guide_sessions
  id (PK), user_id (FK), started_at, completed_at

guide_messages
  id (PK), guide_session_id (FK), role (user/assistant), content, created_at
```

## 7. Development Order

1. **Step 1**: Real-time captioning over WebSocket — a minimal, fully working path from mic input → STT → text shown on screen.
2. **Step 2**: Add the REST-based digital guide mode (LLM conversation).
3. **Step 3**: Add authentication, user settings, and session log retrieval.
4. **Step 4**: Build the CI/CD pipeline and automate cloud deployment.
5. **Step 5**: Harden reliability — retry/fallback logic for STT/LLM failures, etc.

## 8. Frontend Widget Wireframe

A lightweight web widget with two tabs covering the live feature set — minimal navigation, no complex UI. (Unified as a web app rather than a browser extension — see section 11 for the reasoning.)

> **Amended in Sprint 3.** This section originally read "no page navigation" and "no separate screens or routing — everything lives in one widget." Saved text broke that: a saved session has to be reachable by a link, has to survive a reload, and has to be somewhere the browser's own Back button behaves. Both modes still live in the one widget; what moved out are the pages *about* an account's saved text. See `docs/sprint-3.md` for the reasoning.

- **Routes**: `/` is the widget. `/saved` lists the signed-in user's saved text and `/saved/:id` is one session, where it can be read, corrected and downloaded. `/signin` and `/signup` are the account pages. Nothing else has an address.
- **Tabs**: Switches between "caption mode" and "guide mode." Both live in one widget at `/` — no routing between them.
- **Caption mode**: The audio source ("microphone" / "playing audio") is a sub-setting inside caption mode, not a peer of the mode tabs — it's rendered as a small pill-shaped segmented control with a muted "source" label, visually lighter and smaller than the tab buttons above it, so it doesn't read as a third or fourth mode. The status text below it changes with the selection ("Listening via mic…" / "Waiting for tab audio share…"). The most recently confirmed caption line is shown bold; earlier lines fade.
- **Guide mode**: A chat-style UI. Uses the same small pill-control pattern as caption mode — a muted "screen reference" label plus an on/off segment — so both modes share a consistent "tab → sub-setting" visual hierarchy instead of stacking same-weight buttons.
- **Settings**: Only accessibility-critical settings (font size, language) are exposed at the bottom, plus auto-save for a signed-in user — it decides whether their speech is written down at all, which is not a preference to leave hidden. Everything else stays hidden.
- **Header**: Says who is signed in and gets to their saved text. Signed out, it is the way to the account pages.

## 9. Caption Mode — Audio Source Design & Constraints

The two sources are kept clearly separate.

| | Microphone | Playing (tab) audio |
|---|---|---|
| Use case | In-person conversation, live speech in a room | Content playing in a tab, e.g. an uncaptioned lecture video |
| Browser API | `getUserMedia({audio:true})` | `getDisplayMedia({video:true, audio:true})` + tab audio sharing |
| Permission flow | Granted once, persists | User must pick the tab to share every session (cannot be skipped — browser policy) |

**Constraints**:
- Tab audio sharing only works reliably in Chromium-based browsers (Chrome, Edge). Safari has essentially no support.
- macOS cannot capture "full system audio" through browser APIs. If the video plays inside a browser tab, tab audio sharing solves it — but audio from a separate native app cannot be captured this way.
- Having to re-pick the tab every session is friction that can't be removed in a web-app form factor. A one-click flow would require switching to a Chrome extension using the `chrome.tabCapture` API, which is left as a future expansion.

## 10. Guide Mode — Real-Time Screen Analysis Design & Constraints

**Structure**: Rather than continuously watching the screen, the app captures a single screenshot at the moment the user sends a question, and sends it to a multimodal LLM API along with the text question.

1. User clicks "share screen" in guide mode → `getDisplayMedia` prompts them to pick a window/tab/screen (native browser consent dialog)
2. At the moment the question is sent, the current screen is captured via canvas and converted to a base64 image
3. `POST /api/guide/sessions/{id}/messages` sends the question text plus the screenshot together
4. The backend calls a vision-capable LLM API to analyze the screen content and generate the next-step guidance
5. The screenshot itself is not stored — only the response text is logged to `guide_messages` (to avoid retaining sensitive on-screen content)

**Constraints**:
- Most multimodal LLM APIs take single images, not continuous video streams. So this is implemented as "capture and analyze the moment a question is asked," not "continuously understand the screen."
- Screens can show sensitive content (passwords, personal data), so screen sharing must always be explicitly turned on by the user, with an always-visible button to turn it off.
- Reading on-screen text more accurately (via the DOM instead of a screenshot) would require a browser extension. At this stage (web app), screenshot-based analysis is the scoped-in approach.

## 11. Architecture Decision: Web App vs. Browser Extension

The two user groups (seniors in guide mode / students in caption mode) want convenience in different directions.

- **Seniors**: Instant access via a link, with no install, matters most. An extension install is itself a barrier for this group, and Chrome extensions aren't available on mobile at all.
- **Students**: Minimizing friction on repeat use (e.g., one-click tab audio capture) matters more. An extension helps here, but the install barrier still applies equally.

**Decision**: Within the scope of a personal project (5 sprints), unify on a web app. Both groups get the shared benefit of "no install required," in exchange for accepting recurring friction like the tab-selection popup in caption mode. Moving to a browser extension is left as a future improvement once real user feedback comes in.

## 12. Agile Sprint Board (GitHub Projects)

**Board columns**: `Backlog` → `To do` → `In progress` → `In review` → `Done`

**Sprint length**: 2 weeks. The 5-step development order (section 7) maps directly onto the sprints below.

| Sprint | Weeks | Goal | Sample issues |
|---|---|---|---|
| Sprint 1 | 1–2 | WebSocket caption MVP | WebSocket server skeleton / STT API integration / caption UI in the widget / mic input → send |
| Sprint 2 | 3–4 | Guide mode | Implement REST `/api/guide/*` / design LLM prompts / guide mode chat UI |
| Sprint 3 | 5 | Auth & session management | Signup/login API / JWT middleware / session log retrieval API |
| Sprint 4 | 6 | CI/CD & deployment | GitHub Actions workflow / Cloud Run deploy script / env vars & secrets management |
| Sprint 5 | 7 | Reliability hardening | STT/LLM failure retry logic / error handling / incorporate beta feedback |

**Issue conventions**:
- Labels: `frontend` / `backend-rest` / `backend-ws` / `infra` / `bug`
- Every issue lists acceptance criteria as a checklist — e.g. "Reconnects within 5 seconds if the WebSocket connection drops"
- At sprint start, issues are pulled from the backlog into `To do` (sprint planning); unfinished issues roll into the next sprint at sprint end (sprint review)

**What makes this a credible Agile story**: creating a GitHub milestone per sprint, and leaving a short retrospective in the README or commit messages at the end of each sprint — what got done, what didn't — gives you actual evidence that you ran an Agile process, not just a claim that you know what Scrum is.
