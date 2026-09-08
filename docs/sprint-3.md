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

**174 automated tests** — 108 REST, 66 WebSocket. The editing rules have
their own file, `test_caption_sessions_editing.py`, whose point is the
property above: renaming cannot discard an edit, editing cannot discard a
name, and neither ever rewrites `caption_lines`.

Verified by hand in a browser against a live server on a clean port:
signup with a mismatched confirmation (refused before it is sent) and a
matching one (redirected to sign in, not signed in), sign in, the header,
the saved list, rename, delete, download, editing, both prompts, and the
auto-save preference reaching the account. The downloaded file was checked
byte by byte for its BOM.

**Not covered by either.** The live recording path — Stop, Continue and
the manual Save after real speech — needs a microphone and was not
exercised in a browser. Its two halves were checked separately: that
continuing appends rather than overwrites, against the real database; and
that the manual save endpoint behaves, in the test suite.

Also still open, carried from Sprint 2: the WebSocket takes a bare
`session_id` with no token, so anyone holding an id could stream into that
session. Holding the id is the whole authorisation, which is thin, and
Sprint 4 is where it should be fixed.
