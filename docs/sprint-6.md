# Sprint 6 — Accessibility, and evidence for a claim

**Goal** (`Plan.md` §12, amended): audit the accessibility of an
accessibility product, and check the language-switching claim the README
had been making on the strength of three samples.

**Board columns**: `Backlog` → `To do` → `In progress` → `In review` → `Done`

---

## Why there is a sixth sprint

The plan ended at reliability. Two things were left standing that this
project should not have been comfortable with.

**An accessibility tool that had never been audited for accessibility.**
`Plan.md` §1 names two user groups — deaf and hard-of-hearing students,
and seniors — both more likely than average to use a screen reader or a
keyboard alone. Six sprints went by without anyone tabbing through the
app.

That omission was on no carried-forward list, and the reason is worth
stating: every retrospective tracked what had been *deferred*. None
tracked what had never been *considered*. A deferred thing has a name and
keeps reappearing; an unconsidered one is invisible by construction.

**A claim resting on three samples.** The README said captions follow a
speaker who changes language. That was verified by hand on three pairs out
of a hundred and ten, in Sprint 1, and carried forward five times as "the
106 untested language pairs" without anyone deciding whether the claim
should stand in the meantime.

---

## Decisions

### The greys were wrong by the product's own standard

`--text-faded` measured **2.61:1** against a WCAG AA requirement of 4.5.
It is the label on the audio source, the language menu, the settings rows
and the caption placeholder — the text a first-time user reads to work out
what the app does.

Raising it alone would have collided with `--text-muted` at 4.93 and
flattened three levels of emphasis into two, so muted moved down as well.
Both were picked by searching for the nearest grey clearing 4.5 against
the *harder* of the two grounds in each theme, rather than chosen by eye
and checked afterwards.

### `aria-modal` is a claim, not a mechanism

The unsaved-changes dialogs said `role="alertdialog" aria-modal="true"`
and did none of what that implies. Measured before the fix: focus stayed
on the button behind the dialog, **eight controls remained reachable by
Tab**, and Escape did nothing.

For a sighted mouse user that is invisible. For someone on a keyboard it
is a dialog they cannot enter, over a page they are still standing in — at
the one moment in the app where the wrong answer loses their work.

Four properties now hold, each verified in a browser: focus moves in and
lands on **the safe option** rather than the destructive one, Tab cycles
within, Escape takes the way out, and focus returns to whatever opened the
dialog.

### The landmark had been gone for three sprints

`<main className="widget">` became a plain `div` when the router shell
arrived in Sprint 3. A screen reader user had no way to skip the header.
Restored — and deliberately *not* with `display: contents`, which has a
history of removing elements from the accessibility tree and is the last
property to reach for on a landmark that exists to be found.

### The matrix is slow on purpose, and that is the point

`backend-ws/tests/language_matrix.py` synthesises speech in each of the
eleven languages, joins pairs of them, and streams the result through a
real caption server **paced like a microphone**. Recognition behaves
differently when audio arrives faster than it is spoken: the detector
reads three seconds of it, and two of the three switch triggers are
wall-clock.

Eleven syntheses serve all 110 pairs, cached on disk, so every pair hears
identical audio and the run is reproducible. It is a hand-run tool rather
than part of the suite — forty minutes and real money per run — and its
dependency is declared as a `[verify]` extra rather than installed
quietly, because Sprint 4 already paid for that lesson.

---

## Issues

### Issue 26 — Accessibility audit `frontend`
- [x] Contrast measured across the whole palette, both themes, both grounds
- [x] `--text-faded` and `--text-muted` raised past AA without collapsing the hierarchy
- [x] `main` landmark restored, without `display: contents`
- [x] Lighthouse accessibility 94 → 100, desktop and mobile

### Issue 27 — Dialogs that behave like dialogs `frontend`
- [x] Focus moves into the dialog on opening
- [x] It lands on the safe option, not the destructive one
- [x] Tab cycles within and cannot escape into the page behind
- [x] Escape takes the cancel path, leaving edits intact
- [x] Focus returns to whatever opened the dialog

### Issue 28 — Evidence for the language claim `backend-ws`
- [x] A harness that runs any subset of the 110 ordered pairs
- [x] Audio synthesised once per language and cached, so runs are comparable
- [x] Paced like a microphone, because unpaced audio is a different test
- [x] Reproduces the three pairs Sprint 1 verified by hand
- [x] Results written after every pair, so an interrupted run keeps what it learned
- [x] Full matrix run: 68 of 110
- [x] README corrected where it was wrong

---

## Verification evidence

| Check | Evidence |
| --- | --- |
| Contrast was genuinely failing | `--text-faded` at 2.61:1 on the page ground, 2.79 on cards, against AA's 4.5 |
| Contrast now passes on both grounds | 4.65 / 4.98 light, 5.07 / 4.64 dark |
| Lighthouse | 94 → **100**, confirmed on the deployed site under mobile emulation |
| The dialog was not modal | Measured in the browser: focus outside it, 8 controls reachable behind it, Escape inert |
| The dialog is modal now | Focus lands on "Cancel"; three Tabs through three buttons return to it; Escape closes and hands focus back to the opener with edits intact |
| The harness is trustworthy | Reproduces `en→ko`, `ko→en`, `de→fr` — the three Sprint 1 verified by hand |
| Full matrix | 68 of 110 pairs followed the speaker |
| Arabic is a detection fault, not a switching fault | `ar→ko` heard `['hi-IN', 'ko-KR']`: the switch was caught, the language was misnamed |
| The Arabic audio is genuinely Arabic | Pinned to `ar-EG`, the same file transcribes with 71 Arabic characters and zero Devanagari |
| More audio does not fix it | `hi-IN` returned at 3 s, 5 s and 8 s alike |
| Nor does a different speaker | Six Arabic voices, male and female, all detected as Hindi |

### What the run actually found

**One language accounts for nearly half the failures.** Arabic fails 20 of
20; everything else together fails 22 of 90. Reporting "68 of 110" without
that split would have been true and useless.

**The code had already predicted the rest.** A Sprint 2 comment in
`auto.py` says "Related languages fool both cues above." The failures
cluster exactly there — French, Spanish, German and English as targets,
where a stream keeps producing confident finals in the wrong language and
none of the three triggers fires. The comment was right for four sprints,
and nothing had measured what it cost.

---

## Out of scope this sprint

A fourth switch trigger — periodic re-detection regardless of stream
health — which would plausibly recover the stayed-put pairs at the cost of
a detection call every N seconds of every session. That trade is now a
measurable question rather than a guess, and measuring it is one re-run
away.

Uptime checks and alerting, declined for this sprint · Lifting the
one-instance ceiling on the REST API · Cloud SQL backups · A custom domain
· JWT signing key rotation, which still has no procedure · Moving tokens
from `localStorage` to httpOnly cookies · A screen reader driven by
somebody who actually uses one, which is the only audit that finally
counts and is not something this project can perform on itself.
