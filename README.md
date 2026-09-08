# Wayfinder

AI-powered communication and digital accessibility platform.
Full product plan and specification: [`Plan.md`](./Plan.md).

> **Status: Sprint 3 complete — accounts, and text that is kept.**
> Live captioning, guide mode, accounts, and everything an account keeps:
> saved text that can be renamed, corrected and downloaded, and guide
> conversations that can be read back. CI/CD and reliability hardening are
> Sprints 4 and 5 (see `Plan.md` §12).

## Repository layout

| Path | `Plan.md` §3 component | Status |
|---|---|---|
| `frontend/` | React widget and the pages around it | Implemented |
| `backend-ws/` | WebSocket server (caption streaming) | Implemented |
| `backend-rest/` | REST API server (FastAPI) | All of `Plan.md` §4 |
| `backend-ws/app/stt/` | External AI API (STT) | STT and LLM; no TTS in the product |
| `backend-rest/alembic/` | PostgreSQL | Implemented |
| — | GitHub Actions / Cloud Run | Sprint 4 (`Dockerfile`s staged now) |

Documentation and the widget's user-facing strings are both English.
The language being *transcribed* is separate from the interface language:
it is detected by default, and a signed-in user can pin one instead.

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

Both need the same `JWT_SECRET`. `backend-rest` signs access tokens with
it; `backend-ws` only verifies, to know whose transcript a caption stream
may be written to. If they disagree, every signed-in stream is refused and
captioning carries on saving nothing.

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

## Pages

`Plan.md` §8 originally said "no page navigation… everything lives in one
widget", and §8 was amended in Sprint 3 rather than quietly contradicted.
Saved text broke the rule: a saved session has to be reachable by a link,
survive a reload, and leave the browser's Back button meaning what it
says. None of that is true of a panel that opens in place.

| Route | What it is |
|---|---|
| `/` | The widget — captions and guide, still two tabs |
| `/signin`, `/signup` | The account pages |
| `/saved`, `/saved/:id` | Saved text, and one session of it |
| `/conversations`, `/conversations/:id` | Guide conversations, and one of them |

Both modes still live in the one widget at `/`. What moved out are the
pages *about* what an account has kept. The header says who is signed in
and leads to it; the way back is the first thing on every page, in the
same place, always one level up.

An account is optional and is not a gate. Signed out, everything works and
nothing is stored, and the page says so in as many words rather than
leaving it to be worked out.

## Settings that follow you

Text size, caption language, and auto-save are stored on the account, so
they carry to another device rather than being set again each time --
which for a tool whose users need larger text is most of the point of
having an account at all. `Plan.md` §6 had nowhere to keep them, so
`users` gained the three columns.

**Auto-save** decides whether a recording is kept at all, which is why it
is exposed rather than hidden. On, stopping has nothing left to do: the
text is already in the account, and Continue adds to that same entry
instead of starting a second one. Off, nothing is written anywhere until
"Save to my account" is pressed -- the browser makes its own session id
and never asks for a row, so there is nowhere for the words to go.

## Accounts and saved transcripts

Captioning and guide mode work with no account, and in that case nothing
is stored: `POST /api/caption-sessions` returns an id but writes no row,
so `backend-ws` finds none and never writes the transcript down. Signing
in is what turns saving on.

That is why the WebSocket server holds its own database connection. The
captions exist only there, so it is the only thing positioned to write
them, and looking for the session's row is how it learns whether it should
(`Plan.md` §3's diagram shows only the REST server touching the database;
this amends it). Its access is narrow -- find the row, append confirmed
lines, stamp the session finished -- and the schema and migrations belong
to `backend-rest`.

The row also has to be *yours*. A caption stream says who it belongs to in
an `auth` frame carrying an access token, and the lookup is scoped to that
user. Before Sprint 3 closed, an id was the whole authorisation: anyone
holding one could stream audio into that person's saved text. The token
travels in a frame rather than the query string because query strings are
written to every access log.

A correction never overwrites what was recognised. `caption_lines` stays
exactly what the recogniser produced; an edit lands beside it in
`edited_text`, and reading a session returns the kept text where there is
one and the recognised lines otherwise. Every session carries an `edited`
flag, so the interface can be honest about which of the two it is
showing.

## Saving a transcript

"Save as text file" in caption mode downloads everything captioned so far
as a plain `.txt`, one line per caption, oldest first. The file carries a
UTF-8 byte order mark, because these transcripts are often Korean and some
Windows editors read a BOM-less file as the system codepage. It works
signed out, where it is the only copy anyone will get.

Signed in, `/saved` lists everything the account has kept. Each entry can
be renamed, downloaded, or deleted, and opening one shows its text.
"Edit" makes that text editable and "Save" keeps the change. Leaving the
page with unsaved edits is blocked with a warning, and downloading over
them offers to save first. `/conversations` does the reading half of the
same job for guide mode.

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

A signed-in user can pin a language instead, in the settings row. Pinning
turns detection off: someone who has said what they are speaking is
telling us not to guess, and a detector that could overrule them would
make the setting advisory. The trade is that detection handles a speaker
who changes language mid-session and a pinned stream cannot, which is why
"Detect automatically" stays the default.

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

215 tests at the close of Sprint 3: 119 in `backend-rest`, 96 in
`backend-ws`.

The REST tests need PostgreSQL. They run against `wayfinder_test`, never
the development database: `tests/conftest.py` rewrites `DATABASE_URL` to
that name before the app can read it and refuses to start otherwise, since
the schema is dropped and rebuilt for each test. Create it once with
`CREATE DATABASE wayfinder_test OWNER wayfinder;`.

## Sprint log

Per `Plan.md` §12, each sprint closes with a short retrospective here.

### Sprint 3 (week 5) — Accounts, and text that is kept
Issue checklist and verification evidence:
[`docs/sprint-3.md`](./docs/sprint-3.md).

**Delivered.** All of `Plan.md` §4, all six tables of §6, and the pages
that let someone read back, correct, name, download and delete what was
said. 215 tests pass (119 `backend-rest`, 96 `backend-ws`).

**What worked.** Trying to break a thing before trusting it, every time.
Four changes this sprint were verified by *first* demonstrating the
failure they prevent: the migration was run against a populated database
and watched to fail; the drift guard was re-broken to prove it could still
fail; the line-numbering fix was run with the old code to show it
destroying the first two lines of a transcript; and stream authentication
was attacked with a script that took a victim's transcript from 5 lines to
8 before the fix and left it at 5 after. A green test says nothing until
you have seen it go red.

**What surprised us.** Two of the four defects found this sprint were
invisible to the test suite by construction, not by oversight. The
migration needed a table with rows in it, and tests build an empty schema.
The reconnect bug needed two streams against one real session, and the
WebSocket tests have no database. Both would have reached production
untouched. Where a test cannot see the conditions a bug needs, running the
thing for real is not optional.

**What we would do differently.** Three spec sections were amended here --
§8 for routing, §5 twice for the language parameter and the `auth` frame,
§4 for the conversation list. Each was justified and written down, but
they arrived one at a time as the work uncovered them, which meant the
spec spent the sprint slightly behind the code. Reading §4 and §8 against
the sprint's actual scope on day one would have surfaced at least the
routing question before any of it was built.

**Carried forward.** `guide_sessions` can be read but not deleted, which
is an asymmetry with caption sessions and a `DELETE` endpoint away from
being fixed. The 106 untested language pairs from Sprint 2 are still
untested. Retry and fallback for STT and LLM failures remain Sprint 5.

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
