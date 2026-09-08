# Sprint 3 — Accounts, and text that is kept

**Goal** (`Plan.md` §7 Step 3, §12): the `/api/auth/*` and `/api/users/me`
endpoints of §4, the `users`, `refresh_tokens`, `caption_sessions`,
`caption_lines`, `guide_sessions` and `guide_messages` tables of §6, and
the pages that let someone read back, correct and keep what was said.

**Board columns**: `Backlog` → `To do` → `In progress` → `In review` → `Done`

---

## The privacy model, which everything else follows from

Captioning and guide mode both work with no account, and the guarantee
that nothing is kept is structural rather than a rule someone remembered
to apply: **`caption_sessions.user_id` is `NOT NULL`**, so an anonymous
session cannot have a row even by mistake.

backend-ws is never told whether to save. It looks for the row:

```python
found = await connection.scalar(
    text("select 1 from caption_sessions where id = :id"), {"id": self._uuid})
```

No row, no transcript. That one query is the whole policy, and there is no
request field that can turn it off or on by accident — which is also how
auto-save is implemented, below.

---

## Decisions the spec left open

### Section 8 was amended, rather than quietly contradicted

§8 said "no page navigation… everything lives in one widget." Saved text
does not fit that. A saved session has to be reachable by a link, has to
survive a reload, and has to be somewhere the browser's own Back button
behaves — and none of those is true of a panel that opens in place.

The alternatives were to build the list and the detail view as panels
inside the widget, or to add routing and amend the spec. Panels would have
worked and would have left `Plan.md` accurate, but the address bar would
have been lying about where the user was the whole time, and Back would
have left the page instead of leaving the session.

So: `react-router`, five addresses, and §8 amended to say so. Both modes
still live in the one widget at `/`. What moved out are the pages *about*
an account's text:

| Route        | What it is                                    |
| ------------ | --------------------------------------------- |
| `/`          | The widget — captions and guide, two tabs     |
| `/signin`    | Sign in                                       |
| `/signup`    | Create an account                             |
| `/saved`     | Everything this account has kept              |
| `/saved/:id` | One session: read it, correct it, download it |

A **data router** (`createBrowserRouter`) rather than `<BrowserRouter>`,
because `useBlocker` only exists on that one, and stopping someone from
navigating away from unsaved edits is the reason the detail page can be
trusted at all.

### An edit sits beside the transcript, never on top of it

`caption_lines` is what the recogniser produced. It is never rewritten.
A correction goes in a new `caption_sessions.edited_text` column, and
reading a session is:

```python
def _readable_text(session: CaptionSession) -> str:
    if session.edited_text is not None:
        return session.edited_text
    return "\n".join(line.text for line in session.lines)
```

The alternative — editing the lines in place — is simpler and destroys
information. Kept apart, a correction can be undone, and it stays clear
which words came from the machine and which from the person. The API says
so too: every session carries an `edited` flag, so the interface can be
honest about which of the two it is showing.

### Auto-save is a property of the account, not of the recording

It follows someone to another device, like text size. It also decides
whether a session row exists at all, which is what makes it real rather
than cosmetic:

- **On** — `POST /api/caption-sessions` creates the row, backend-ws finds
  it, and each confirmed line is written as it is confirmed. Stopping has
  nothing left to do; the text is already there.
- **Off** — the browser makes its own id with `crypto.randomUUID()` and
  never calls that endpoint. No row, so backend-ws writes nothing, exactly
  as for an anonymous listener. The text exists only in the tab until the
  user presses Save.

Stopping offers the same two choices either way — Reset and Continue —
because carrying on is a question about the recording and auto-save is a
question about where the words go. The first draft made Save *replace*
Continue when auto-save was off, which quietly removed the ability to
carry on from the people who had turned saving off, and was corrected.
Saving by hand sits with "Save as text file" instead, where the other
"keep this" action already was.

Saving twice updates one entry rather than making a second. Save, then
Continue, then Save again would otherwise leave two entries with the first
one's text duplicated inside the second, so the first save keeps its id
and later ones `PATCH` it — the same promise Continue makes with auto-save
on, kept on the manual path too.

This is why "off" needed no new request field and no flag on the socket:
*not creating the row* is the whole implementation, and it reuses a path
that already had to be right.

### Continuing a recording extends the entry instead of starting one

`POST /api/caption-sessions/saved` is the one place the server stores words
it never heard, so the text lands in `edited_text` and `caption_lines`
stays empty — the lines table means one thing only.

Continue is the other half. The browser holds the session id across a stop
and reopens the same session, and `CaptionStore` places the new stream's
line numbers after whatever is already stored:

```python
self._base_seq = await connection.scalar(
    text("select coalesce(max(seq) + 1, 0) from caption_lines "
         "where session_id = :id"), {"id": self._uuid})
```

**This fixed a live bug, not just Continue.** A stream numbers its lines
from zero, and so does the stream that replaces it after a dropped socket.
Before this, a reconnect mid-session wrote line 0 over line 0 — the
`on conflict … do update` that was there to stop duplicates was silently
destroying the beginning of the transcript instead. Checked both ways
against the real database: with the fix, four lines; without it, the first
two were gone and only the last two remained.

### A pinned language replaces detection rather than joining it

§8 lists language beside text size as one of the two accessibility
settings. The column, the `PATCH` field and the client type all existed;
nothing used them, and nothing carried the choice to the recogniser.

The obstacle is that backend-ws is handed a `session_id` and nothing else.
Three ways across were considered:

1. **Read it from the database** through the session row's `user_id`. No
   protocol change at all — but it only works when there *is* a row, so a
   listener with auto-save off would silently lose their language. Tying
   "which language" to "am I saving" is a coupling a user would experience
   as a bug.
2. **Put it in the first client message.** §5's client messages are
   `audio_chunk` and `end_stream`; adding a field to either invents one.
3. **An optional query parameter**, which is what was built.

`?session_id=…&language=ko-KR`. Absent means detect, which is byte for byte
what every session sent before the setting existed. This amends §5; it was
flagged before it was written, and §5 now says so.

Pinning turns detection **off** — `dataclasses.replace(settings,
stt_language=tag, stt_auto_detect=False)`. A detector that could still
overrule the choice would make the setting advisory, and someone who has
said what language they are speaking is telling us not to guess. The trade
is real and worth stating: auto-detect handles a speaker who changes
language mid-session, and a pinned stream cannot. That is why "Detect
automatically" is first in the menu and stays the default.

A malformed tag is logged and ignored rather than fatal. A preference
should never be the reason captions do not start.

The check is a *shape*, not a list, matching `PATCH /api/users/me`
exactly: pinning a language the recogniser supports but detection does not
is a legitimate thing to want. The widget's menu offers the eleven
Wayfinder claims to support; the socket accepts any well-formed tag. What
is offered and what is allowed are deliberately different.

One consequence falls out of §5 rather than being designed:
`caption.language` is reported "only when the language was detected rather
than configured", so a pinned session reports `null` throughout. The chip
still names the pinned language, in muted styling — it is the user's own
choice read back to them, not news.

### An id is a name for a stream, not permission to write to a transcript

Until this sprint closed, `backend-ws` took a bare `session_id` and asked
only whether a row with that id existed. Anyone who learned an id could
open a socket and have lines written into that person's saved text.
Holding the id *was* the authorisation.

That is a thin claim to make in the sprint whose goal is "Signup/login API
/ JWT middleware", so it was fixed rather than carried forward.

**Where the token goes.** A browser cannot set headers on a WebSocket, so
the usual four options are a query parameter, the `Sec-WebSocket-Protocol`
header, a first-message handshake, or a single-use ticket from a new REST
endpoint. The query parameter is the common choice and is disqualified
here on evidence rather than principle: this project's own uvicorn logs
the full request line, which is how the `language` parameter was verified
earlier in this sprint. A JWT there would be in every access log. The
ticket would have meant a new §4 endpoint, and §4 is the part of the spec
this project is most careful with. So: a first frame, and a §5 amendment,
which §5 already had precedent for.

```json
{ "type": "auth", "token": "<access token>" }
```

**Optional, and first or not at all.** No frame is an anonymous stream,
which captions normally and reaches no database — unchanged, and still the
common case. Sending `auth` later is an error the stream survives, because
a confused client is not a reason to cut off someone's captions, but
identity cannot change hands part-way through a transcript.

**A bad token fails loudly; a mismatched session fails quietly.** These
are deliberately different. An unverifiable token means the client claimed
an identity it does not have: one `error`, then close with 1008, because
someone who believes they are signed in must not caption for ten minutes
and only then find nothing was kept. A *valid* token for a session
belonging to someone else simply does not save — answering any louder
would confirm that the id exists, which is exactly what
`GET /api/caption-sessions/{id}` returns 404 to avoid.

**The store now asks a different question.** `select 1 from
caption_sessions where id = :id` became `... where id = :id and user_id =
:user_id`, and no verified user means no query at all. The privacy model
did not change shape — it is still "no row, no transcript" — but the row
now has to be *yours*.

**What the two services share.** `JWT_SECRET`, and the payload shape.
Nothing else: no models, no session, no call between them.
`backend-ws/app/tokens.py` deliberately mirrors `backend-rest`'s constants
rather than importing them, because they are separate packages in separate
environments. That is the price of verifying a token without a network hop
on every connection, and it is written down so nobody later assumes the
duplication is an accident. A service started with no `JWT_SECRET` refuses
every token rather than accepting them unchecked.

**Reconnects re-authenticate.** Each connection is a new session on the
server, so the frame goes out again every time the socket comes back — and
the client fetches a *fresh* token each time rather than reusing the one it
started with, since access tokens last fifteen minutes and a lecture does
not. The client also drops audio between a socket opening and its auth
frame going out: a chunk that overtook it would make the server read the
whole stream as anonymous, and the transcript would stop being saved with
nothing appearing to go wrong.

### Auto-save governs guide mode too, and reuses the anonymous path

The same setting, not a second one: "keep what I do here" is one decision,
and two switches would be two things to get wrong.

Guide mode cannot do what captions do with auto-save off, though. A
caption transcript can live entirely in the browser because the server
needs no memory of it; a conversation cannot, because the model needs the
earlier turns to answer a follow-up. It has to be held *somewhere*.

It already was. An anonymous conversation is held in this process and
forgotten, and auto-save off is exactly that arrangement for someone who
happens to have an account — so the client sends no token when starting
one, and the server takes the path it already had. No new field, no flag,
and the "does this reach a table" question still has one answer.

`POST /api/guide/sessions/{id}/save` then writes it, and takes **no body**.
The server has its own copy, so it saves what it actually said rather than
what a browser hands back — the same principle as `caption_lines` being
what the recogniser produced. A client cannot put words in the assistant's
mouth by asking for them to be saved.

Saving twice adds the turns since rather than a second copy, which is the
same promise Continue makes for captions. Two edges are refused rather
than fudged: a conversation this process no longer holds cannot be saved
(better than writing an empty one and calling it kept), and one that was
saved and then deleted cannot be saved again (that would resurrect
something the person threw away).

### Guide mode has no Continue button, because it never stopped

The request asked for save, continue and reset in guide mode, matching
captions. Two of those built directly. Continue did not, and the reason is
worth writing down rather than quietly dropping.

Captioning has a Stop, so Continue is a real state change: pick the
microphone back up. A conversation has no Stop — you continue it by asking
the next question, and the box to do that is already on screen. The only
place a Continue *button* could go is after "Finish this conversation",
and there it would mean one of two bad things: reopening a session the
server has deliberately closed, or starting a new one that the model has
no history for, which is the whole value of guide mode.

So guide mode's buttons are Reset, Finish, and — with auto-save off —
Save. Continuing is asking.

### Creating an account does not sign you in

Signup answers with tokens and they are deliberately dropped. Someone who
has just chosen a password types it once more on the sign in page, which is
both the confirmation that it was memorable and the moment they learn where
signing in happens — every time after this, that is the page they start
from.

### Two prompts, two different mechanisms

- **Leaving the page in-app** — `useBlocker`, and our own dialog, so it
  reads "You have unsaved changes." exactly.
- **Closing the tab or reloading** — `beforeunload`, where the browser
  insists on its own wording. That is the warning existing, not the warning
  reading the way the rest of the page does. Nothing can be done about it;
  it is worth knowing rather than worth hiding.

Deleting a session and downloading over unsaved edits both ask first — the
first because it cannot be undone, the second because the user probably
wanted the corrected version.

---

## Naming that departs from the request, and why

The request called the manual control a "Save button". It is labelled
**"Save to my account"**, because it sits next to "Save as text file" and
plain "Save" beside that would have been a coin toss. Once something has
been saved and the recording carried on, it reads "Save the rest to my
account", which is what the button now does.

The request also said Save should *replace* Continue when auto-save is
off. Built that way first, then corrected on feedback: it took carrying on
away from exactly the people who had turned saving off, for no reason —
the two decisions are unrelated. Reset and Continue are now the same pair
in both modes.

---

## Issues

### Issue 10 — Accounts and tokens `backend-rest`
- [x] `POST /api/auth/signup` creates an account and returns tokens
- [x] `POST /api/auth/login` answers identically for a wrong password and an unknown email
- [x] `POST /api/auth/refresh` rotates the refresh token
- [x] `DELETE /api/auth/logout` revokes it, so a signed token can be withdrawn
- [x] Access tokens are short-lived JWTs; refresh tokens are opaque and stored only as a SHA-256 hash
- [x] Passwords are argon2; a login rehashes when the parameters have moved on
- [x] Email is lower-cased on the way in

### Issue 11 — Schema and migrations `backend-rest`
- [x] All six tables of §6, plus `refresh_tokens`
- [x] `caption_sessions.user_id` is `NOT NULL`, so an anonymous session cannot have a row
- [x] Alembic migrations, with a test that fails when the models and the migrations disagree
- [x] Deleting an account takes its sessions, lines and conversations with it

### Issue 12 — Settings that follow the account `backend-rest` `frontend`
- [x] `GET`/`PATCH /api/users/me` for `font_size`, `caption_language`, `auto_save`
- [x] Partial update in the real sense: sending null clears, omitting leaves alone
- [x] Text size applies on load and is saved as it changes
- [x] The language menu offers the eleven supported languages plus "Detect automatically"
- [x] A pinned language reaches the recogniser and turns detection off
- [x] Auto-save is exposed rather than hidden, because it decides whether speech is kept at all
- [x] Stopping offers Reset and Continue whether auto-save is on or off
- [x] Saving by hand twice updates one entry rather than making a second

### Issue 13 — Saved text `backend-rest` `frontend`
- [x] `GET /api/caption-sessions` lists mine, newest first
- [x] `POST /api/caption-sessions/saved` keeps a transcript the widget was holding
- [x] `PATCH /api/caption-sessions/{id}` renames or corrects, without one discarding the other
- [x] `DELETE /api/caption-sessions/{id}` removes a session and its lines
- [x] `caption_lines` is never rewritten by an edit
- [x] Another person's session is 404, never 403
- [x] `/saved` lists, renames, downloads and deletes; `/saved/:id` reads and corrects
- [x] Unsaved edits block navigation and the tab close, and offer to save before a download

### Issue 14 — Continuing a recording `backend-ws` `frontend`
- [x] Continue reopens the same session rather than starting a second entry
- [x] Stored line numbers resume after what is already written
- [x] A reconnect appends rather than overwriting the start of the transcript

### Issue 15 — Whose stream it is `backend-ws` `frontend`
- [x] `auth` frame carrying an access token (§5, amended)
- [x] Optional and first-or-not-at-all; a late frame errors without dropping the stream
- [x] A token that does not verify is refused with one `error` and close 1008
- [x] The store matches on `user_id`, so another person's id writes nothing
- [x] No `JWT_SECRET` means every token is refused rather than accepted unchecked
- [x] Reconnects re-authenticate with a freshly fetched token
- [x] The token appears in no access log

### Issue 16 — Conversations that can be read back `backend-rest` `frontend`
- [x] `GET /api/guide/sessions` lists mine (§4, amended)
- [x] Named by the first question asked, counted in questions rather than messages
- [x] Anonymous conversations never appear, because they belong to nobody
- [x] `/conversations` and `/conversations/:id` behind the same header button as saved text
- [x] Auto-save governs guide mode too, from the one setting
- [x] Off, a conversation reaches no table until `POST .../save` is asked for
- [x] What is saved is the server's own copy, never one sent from the browser
- [x] Saving again after carrying on adds the turns since, not a second copy
- [x] A conversation this process no longer holds, or one already deleted, is refused
- [x] `PATCH` renames and `DELETE` removes, as for caption sessions (§4, amended)
- [x] `guide_sessions.title` (§6, amended)

### Issue 17 — Pages `frontend`
- [x] `react-router` data router; §8 amended and the reasoning recorded
- [x] Confirm-password on signup, refused before the request is sent
- [x] Creating an account redirects to sign in rather than signing in
- [x] "Saved Text List" sits to the left of "Sign out" in the header
- [x] The way back is the first thing on every page, always one level up

---

## Verification evidence

| Check | Evidence |
|---|---|
| Whole suite | 119 passed in `backend-rest`, 96 in `backend-ws`; frontend build clean |
| Migration against real data | `alembic upgrade head` on the populated development database: failed with `NotNullViolationError`, rolled back cleanly, fixed, re-run, existing row adopted `true` |
| Drift guard actually guards | Run twice for repeatability, then a model deliberately broken to confirm it still fails |
| Continue extends one entry | Real microphone: Start, Stop, Continue, Stop produced one row, 14 lines, seqs 0–13, no gaps, from two streams of 5 and 9 |
| Continue's fix is the fix | Old code restored: first two lines destroyed, only the last two remained |
| Auto-save off | Stop offered Reset, Continue and Save; the save landed; the button locked against a second |
| Saving twice keeps one entry | Save, Continue, Save again: one entry holding all 19 lines, not two with the first duplicated inside the second |
| Pinned language on the wire | Server log: `?session_id=…&language=ko-KR` pinned, no parameter at all on "Detect automatically" |
| Pinning is not advisory | `stt_auto_detect` forced back on: `test_pinning_turns_detection_off` fails |
| Stream auth stops the attack | Script streaming into a victim's session id with no token: transcript stayed at 5 lines |
| The attack was real | Old store code restored: the same script took it from 5 lines to 8 |
| Only the owner writes | Four callers at the store — owner, stranger, anonymous, bogus id — one write; old code let all four through |
| The token is not logged | Zero occurrences in the WebSocket access log after a signed-in recording |
| Unsaved-changes guards | In-app navigation blocked with the exact wording; download offered save first; both dialogs read from the accessibility tree |
| Downloaded file | Byte-inspected: `efbbbf` BOM, title-derived filename, content including the saved edit |
| Signup does not sign in | Mismatched confirmation refused before the request; matching one landed on `/signin` with the header still signed out |
| Conversations reachable | Seeded two turns, listed at `/conversations` named by the opening question, opened and both turns rendered |
| Guide auto-save off keeps nothing | Asked a question with the setting off: `GET /api/guide/sessions` returned zero before Save was pressed |
| Guide save, carry on, save again | One conversation, 2 exchanges, 4 messages in `user, assistant, user, assistant` order — no duplicated beginning |
| Rename and delete a conversation | Renamed in place to "Sending money to Mina", then deleted behind the two-step confirm; the list went back to empty |

---

## Bugs worth remembering

### The migration that would have passed every test and failed every deploy

`auto_save` is `NOT NULL`, and autogenerate produced a bare `add_column`.
Against a table with rows in it that is:

```
NotNullViolationError: column "auto_save" of relation "users"
contains null values
```

Tests build an empty schema from scratch, so no test would ever have seen
it — the failure needs an existing row. It was proved by running the
migration against the development database, watching it fail, and watching
it roll back cleanly. Fixed with `server_default=sa.text('true')` on both
the migration and the model, then applied for real: the existing row
adopted `true`.

The general form: **a migration's correctness depends on data the tests do
not have.** Any `NOT NULL` column added to a populated table needs a server
default, and the only way to know is to run it somewhere with rows.

### The drift guard that only worked once

`Base.metadata.drop_all` leaves `alembic_version` behind, so on the second
run Alembic read itself as already at head and upgraded nothing — the test
passed by doing no work. Fixed by dropping the version table too, then run
twice to prove repeatability, then re-broken on purpose to prove it can
still fail.

### `.env` pointed the test suite at the real Gemini API

Loading `.env` in `conftest.py` made three tests take 20 seconds instead of
0.19. `WAYFINDER_LLM=mock` is now pinned before config is imported. The
same file also rewrites `DATABASE_URL` to `wayfinder_test` and asserts it,
so a mistake here cannot reach the development database.

---

## What is tested, and what is not

**232 automated tests** — 136 REST, 96 WebSocket. Two files exist for a
property rather than an endpoint: `test_caption_sessions_editing.py`, for
renaming and editing never discarding each other or rewriting
`caption_lines`; and `test_stream_auth.py`, for a stream having to say
whose it is. Both were re-broken on purpose to confirm they fail.

The evidence table above is the run-by-run detail. What no automated test
covers is the live recording path — it needs a microphone — so that was
exercised by hand, and the WebSocket store has no test database at all, so
its two changes were checked with scripts against the real one.

### The privacy model failing safe, mistaken for a bug

During the microphone run, `backend-ws` was first started without
`DATABASE_URL`. It fell back to `.env`, looked for the session in the
*development* database, found nothing, and correctly wrote nothing. The
zero-line result looked exactly like a bug for a minute.

It is worth keeping because it shows the cost of the design as well as its
value: "no row, no transcript" fails closed and says nothing, which is the
right behaviour for privacy and an actively misleading one for an operator
who has misconfigured a service. If this ever runs somewhere real, a
signed-in session that finds no row deserves a log line at warning level.

---

## Out of scope this sprint

The 106 untested
language pairs carried from Sprint 2 · TTS (§3 lists it, §12 places it in
no sprint) · GitHub Actions and Cloud Run (Sprint 4) · STT and LLM retry
and fallback (Sprint 5) · Moving tokens from `localStorage` to httpOnly
cookies, which is the hardening if this ever leaves a portfolio.
