# Sprint 2 — Digital guide mode

**Goal** (`Plan.md` §7 Step 2, §12): the REST-based guide mode — the
`/api/guide/*` endpoints of §4, the LLM conversation flow, and the chat UI
of §8 including the screenshot design in §10.

**Board columns**: `Backlog` → `To do` → `In progress` → `In review` → `Done`

---

## Decisions the spec left open

§4 names the endpoints but not every field, so these were settled before
any code was written rather than invented mid-implementation.

### The message body's text field is `content`

§4 names only `screenshot`, describing the other half as "the text
question". `content` was chosen over `text` or `question` so that the
request field, the `guide_messages.content` column in §6, and the `GET`
response all use one word for the same value. A follow-up turn like "yes,
that worked" is also not a question, which `question` would have implied.

### The model is Gemini 2.5 Flash, reached through Vertex AI

§10 requires a vision-capable LLM but names none. Vertex was chosen over a
direct API so the server authenticates with the same Application Default
Credentials as speech-to-text — this project's organisation blocks
service-account keys, and a second API key would be a second thing to
manage in Sprint 4's deployment.

Two settings are not defaults and should not be "tidied up":

| Setting | Why |
|---|---|
| `thinking_budget=0` | Gemini 2.5 spends part of `max_output_tokens` on internal reasoning. With it on, answers were cut off mid-sentence. Guide replies are two or three sentences and do not need it. Also roughly halves latency. |
| `GEMINI_LOCATION=us-central1` | Regional endpoint, matching where this project's speech models already run. |

### Response bodies are derived from §6

§4 specifies no response shapes, so they follow the schema columns:
sessions return `id` / `started_at` / `completed_at` / `messages`, and
messages return `id` / `role` / `content` / `created_at`.

### Deferred: authentication

`guide_sessions.user_id` is a FK in §6, but auth is Sprint 3 (§7 step 3).
Sessions are stamped with a `PLACEHOLDER_USER_ID` constant so the column
has the shape §6 calls for without inventing a login ahead of schedule.
Storage is in memory, as caption sessions have been since Sprint 1;
PostgreSQL arrives with auth.

> **Resolved in Sprint 3.** The placeholder is gone. A signed-in
> conversation is rows; a signed-out one stays in this process and is
> never written, because the model needs the earlier turns to answer a
> follow-up but nobody asked for it to be kept.

---

## Issues

### Issue 6 — Guide endpoints `backend-rest`
- [x] `POST /api/guide/sessions` starts a session and returns a `session_id`
- [x] `POST /api/guide/sessions/{id}/messages` takes `content` plus optional `screenshot` and returns the assistant reply
- [x] `GET /api/guide/sessions/{id}` returns the conversation in order
- [x] `PATCH /api/guide/sessions/{id}/complete` sets `completed_at`; completing twice keeps the first timestamp
- [x] Both turns are stored with `role` of `user` or `assistant` (§6)
- [x] An unknown session is 404; a completed session refuses new messages with 409
- [x] No endpoint or request field outside §4 was added
- [x] `pytest` covers all of the above against the mock model

### Issue 7 — LLM conversation flow `backend-rest`
- [x] `GuideModel` interface: `respond(history, question, screenshot, mime)`
- [x] Mock adapter (`WAYFINDER_LLM=mock`) needs no cloud project
- [x] Gemini adapter passes earlier turns so follow-up questions have context
- [x] The system prompt targets §1's user group: one step at a time, plain words, the exact on-screen label in quotes
- [x] The prompt refuses to describe a screen it has not been shown
- [x] The prompt declines to read back passwords or payment details
- [x] Replies come back in the language the question was asked in
- [x] A model failure returns 502 and stores nothing, so a retry is clean

### Issue 8 — Screenshot capture `frontend`
- [x] `getDisplayMedia` prompts for a window or screen when sharing is turned on (§10 step 1)
- [x] A single frame is captured via canvas at the moment the question is sent (§10 step 2)
- [x] The capture is downscaled to a 1280 px long edge and encoded as JPEG
- [x] `screenshot` is sent only while sharing is on, and omitted entirely otherwise
- [x] Stopping the share from the browser's own bar turns the pill off
- [x] The screenshot never reaches storage (§10 step 5)

### Issue 9 — Guide mode chat UI `frontend`
- [x] The guide tab is enabled and switches without routing (§8)
- [x] A muted "screen reference" label plus an on/off pill, matching caption mode's pattern (§8)
- [x] Chat transcript: the question stays quiet, the answer carries the weight
- [x] The composer sends on Enter, with Shift+Enter for a new line
- [x] A "Looking…" line while the model is working
- [x] The conversation can be finished, and a new one started after
- [x] Font size from the settings bar applies to the transcript

---

## Verification evidence

| Check | Evidence |
|---|---|
| Endpoints | `pytest` in `backend-rest`: 30 passed, 22 of them guide |
| Nothing regressed | `pytest` in `backend-ws`: 54 passed; frontend build clean |
| Routes match §4 exactly | OpenAPI lists the four guide paths and no others |
| Reads a real screen | Synthetic banking screen sent to Gemini: "press the green button that says \"Confirm\" at the bottom right" — correct button, correct position, 2.4 s |
| Conversation history reaches the model | A follow-up with no screenshot referred back to "Confirm" from the previous turn |
| Language follows the question | The same screenshot asked about in Korean answered in Korean |
| Screenshot is never stored | `GET` after a screenshot turn contains no image data; message keys are exactly `id`, `role`, `content`, `created_at` |
| Completed sessions are closed | `PATCH .../complete` then `POST .../messages` returns 409 |
| Screenshot validation | Malformed base64 and unsupported types return 422; over 4 MB returns 413 |
| Widget end to end | Guide tab → question → reply rendered, with the pill reporting sharing off and the mock confirming no screenshot was sent |

### One defect found by live testing

Asked "what happens after I press it?", the model narrated a screen it had
never seen — "a new screen will appear… your payment was successful". The
prompt already forbade inventing UI, but not *predicting* it, and for
someone being walked through a bank transfer a confident description of a
screen that may not appear is the worst failure this feature has.

Reproduced across repeated runs, then fixed by making the rule explicit
about the next screen specifically. It now answers: "I cannot see what
happens after you press \"Confirm\" yet. Please press it and then ask me
again." Verified stable across repeated runs.

## Out of scope this sprint

Auth, JWT, and real `user_id` (§4, Sprint 3) · PostgreSQL persistence of
`guide_sessions` and `guide_messages` (§6, Sprint 3) · TTS (§3 lists it,
§12 does not put it in this sprint) · GitHub Actions and Cloud Run
(Sprint 4) · LLM retry and fallback (Sprint 5).

> `tab_audio` capture (§9) was listed here as out of scope, and in Sprint 1
> before that. It is described in §3, §4, §5, §6, §8 and §9 but never
> appears in the §12 sprint table, so it was designed and then never
> scheduled. Built after Sprint 2 closed, once that gap was noticed.
