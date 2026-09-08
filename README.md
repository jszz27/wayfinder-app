# Wayfinder

AI-powered communication and digital accessibility platform.
Full product plan and specification: [`Plan.md`](./Plan.md).

> **Status: Sprint 2 complete — guide mode.**
> A minimal working path from microphone input, through the WebSocket
> server, to STT, to captions rendered in the widget. Guide mode, auth,
> persistence, and CI/CD are later sprints (see `Plan.md` §12).

## Repository layout

| Path | `Plan.md` §3 component | Sprint 1 status |
|---|---|---|
| `frontend/` | Lightweight React widget | Implemented |
| `backend-ws/` | WebSocket server (caption streaming) | Implemented |
| `backend-rest/` | REST API server (FastAPI) | Health, caption sessions, guide mode |
| `backend-ws/app/stt/` | External AI API (STT) | STT only; no TTS or LLM yet |
| — | PostgreSQL | Sprint 3 |
| — | GitHub Actions / Cloud Run | Sprint 4 (`Dockerfile`s staged now) |

Documentation and the widget's user-facing strings are both English.
The language being *transcribed* is separate from the interface language
and is set by `STT_LANGUAGE`.

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

Both services read the repository's `.env` themselves at startup, so no
flag is needed. Real environment variables take precedence over the file,
which is what lets a deployment set its own configuration.

## Guide mode

The second tab is a chat: the user describes what they are stuck on and
gets one next step back in plain language. Turning on "screen reference"
starts a browser screen share; a single frame is then captured at the
moment each question is sent and passed to a vision model along with the
text (`Plan.md` §10).

The screenshot is never stored. It is decoded, used for that one question,
and dropped — only the text of both turns is kept, so nothing sensitive
that happened to be on screen is retained.

`WAYFINDER_LLM=mock` runs the whole flow, screenshot path included, with
no cloud project. `WAYFINDER_LLM=gemini` uses Gemini 2.5 Flash through
Vertex AI, authenticating with the same credentials as speech-to-text.

Issue checklist and evidence: [`docs/sprint-2.md`](./docs/sprint-2.md).

## Stopping, and carrying on

Stopping with a transcript on screen offers two ways forward rather than
one. "Continue" keeps what is there and records after it; "Reset" clears
it and leaves the widget idle, back at a plain "Start" -- discarding a
transcript and deciding to record again are two decisions, not one. The transcript belongs to the widget, not to a
recognition session, so a session can be continued with a different audio
source -- stop while captioning a video, switch to the microphone, and
continue into the same transcript.

Each continued session numbers its caption lines from zero again, so
incoming lines are shifted past the ones already on screen. Without that
they would merge onto the existing transcript and overwrite it.

## Captioning playing audio

The "playing audio" source captions sound the user is already listening to
-- a video with no captions, or automatic ones that are not good enough --
by having the browser hand the audio over directly rather than holding a
microphone up to the speakers (`Plan.md` §9).

Three constraints come from the browser, not from this app. It is Chromium
only. What can be shared depends on the platform: sharing a tab gives that
tab's audio anywhere, while sharing a whole screen offers system audio on
Windows but not on macOS, which cannot capture a native app's sound at
all. And the choice cannot be remembered, so it has to be made every
session.

## Saving a transcript

"Save as text file" in caption mode downloads everything captioned so far
as a plain `.txt`, one line per caption, oldest first. The file carries a
UTF-8 byte order mark, because these transcripts are often Korean and some
Windows editors read a BOM-less file as the system codepage.

## Punctuation

Captions are punctuated as they are spoken, on interim results as well as
confirmed ones, so sentence boundaries appear live rather than arriving at
the end. Periods and question marks are produced; exclamation marks are
not, because Google's punctuation model does not emit them.

## Language

`STT_AUTO_DETECT=true` works the language out from the opening seconds of
audio and shows it beside the status line. English, Korean, Spanish,
Mandarin, Japanese, French, Hindi, Arabic, Portuguese, German and Russian
are recognised; anything else falls back to `STT_LANGUAGE`. All eleven were
verified end to end against synthesised speech in each language.

`DETECT_SECONDS` in `app/stt/auto.py` trades startup delay against
accuracy. At three seconds all eleven languages are identified and the
first caption arrives about five seconds in. At two seconds the first
caption arrives about 3.5 seconds in, but Arabic is misread as Hindi.

If the speaker changes language mid-session, the caption follows. Google's
streaming models transcribe one language per stream -- given several codes
they pick one and drop the rest -- so the only option is to open a new one,
which means noticing that the old one has gone wrong. A stream fed the
wrong language may collapse in confidence, stop returning results, or keep
revising a line that never settles, depending on the pair; all three are
watched for. Any of them prompts a fresh detection, and a genuinely
different answer opens a new stream with the recent audio replayed.
Captions resume in the new language within a few seconds. Verified on
English to Korean, Korean to English, and German to French.

Google has no single streaming model that both detects a language and
returns interim results, so two are used for what each is good at. One
short synchronous `chirp_2` call names the language, then the session
streams on `long`, pinned to it. The cost is about three seconds at the
start of a session; captions are word-by-word live from then on. Detection
needs a regional endpoint (`GOOGLE_DETECT_LOCATION`) because `chirp_2`
does not exist in `global`.

The interface language is separate and is English throughout.

## Tests

```powershell
cd backend-ws;   pytest
cd backend-rest; pytest
cd frontend;     npm run build    # type-check + bundle
```

The REST tests need PostgreSQL. They run against `wayfinder_test`, never
the development database: `tests/conftest.py` rewrites `DATABASE_URL` to
that name before the app can read it and refuses to start otherwise, since
the schema is dropped and rebuilt for each test. Create it once with
`CREATE DATABASE wayfinder_test OWNER wayfinder;`.

## Sprint log

Per `Plan.md` §12, each sprint closes with a short retrospective here.

### Sprint 2 (weeks 3–4) — Guide mode
Issue checklist and verification evidence:
[`docs/sprint-2.md`](./docs/sprint-2.md). Retrospective to be written at
sprint review.

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
