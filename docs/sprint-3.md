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
plain "Save" beside that would have been a coin toss. Reset is shown with
auto-save on as well as off, since it was asked for in Sprint 2 and
removing it when the preference changed would have been a regression.

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

**204 automated tests** — 108 REST, 96 WebSocket. The editing rules have
their own file, `test_caption_sessions_editing.py`, whose point is the
property above: renaming cannot discard an edit, editing cannot discard a
name, and neither ever rewrites `caption_lines`.

Verified by hand in a browser against live servers on clean ports:
signup with a mismatched confirmation (refused before it is sent) and a
matching one (redirected to sign in, not signed in), sign in, the header,
the saved list, rename, delete, download, editing, both prompts, and both
preferences reaching the account. The downloaded file was checked byte by
byte for its BOM.

The recording path was exercised end to end with a real microphone:

- **Auto-save on.** Start, Stop, Continue, Stop produced **one** session
  row holding 14 lines numbered 0-13 with no gaps and no overwrites, from
  two separate streams of 5 and 9 — which is the whole claim Continue
  makes.
- **Auto-save off.** Stop offered Reset and Save rather than Continue, the
  save landed in the account, and the button then locked itself against a
  second one.
- **Language.** With Korean pinned the socket opened as
  `?session_id=…&language=ko-KR`; with "Detect automatically" it opened
  with no parameter at all. Both read from the server's own log. The menu,
  the source pill and the auto-save toggle all lock while a stream is open.

One thing to know about that run: backend-ws was first started without
`DATABASE_URL`, so it fell back to `.env` and looked for the session in
the *development* database, found nothing, and correctly wrote nothing.
The zero-line result was the privacy model working, not a bug — but it is
a good illustration of how quietly "no row, no transcript" fails safe, and
of why the two services must be pointed at the same database.

The stream authentication was demonstrated by attack, not by assertion.
A script opened a socket on a signed-in user's session id, with no token,
and pushed enough audio for three confirmed lines:

- **With the fix**: the attacker received its own captions — anonymous
  captioning still works — and the victim's transcript stayed at 5 lines.
- **With the old code restored**: the same script took the transcript from
  5 lines to 8. The attacker's words were in someone else's saved text.

The same pair of runs was done at the store level with four callers — the
owner, a stranger, an anonymous listener and a bogus user id. Only the
owner could write; the old code let all four through. And the access log
was checked afterwards for the token: zero occurrences, which was the
whole reason it travels in a frame.
