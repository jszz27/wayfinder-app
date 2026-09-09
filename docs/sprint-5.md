# Sprint 5 — Reliability hardening

**Goal** (`Plan.md` §7 Step 5, §12): retry and fallback for STT and LLM
failures, and error handling worth the name.

**Board columns**: `Backlog` → `To do` → `In progress` → `In review` → `Done`

---

## The defect that mattered most

Google caps a streaming recognition at a few minutes. This app captions
lectures.

Nothing handled the end of a stream, and the two ways it can end were both
bad, in different ways:

- **It raises.** `_forward_captions` caught it, sent one error, and closed
  the socket. Captioning died mid-sentence.
- **It simply finishes.** The forwarding task ran out, the receive loop
  carried on accepting audio, and captions stopped with no error, no
  close, and nothing on screen to explain it.

The second is worse. A user cannot report "it stopped"; they assume they
did something wrong. And it would have appeared only in sessions longer
than a few minutes — which is to say, in exactly the sessions this product
exists for, and never in a test or a demo.

## Decisions

### The stream is not the session

`ResilientSttStream` wraps any adapter and opens another when one ends
early. The listener sees a short gap rather than the end of their
transcript.

Three details carry the weight:

**The last two seconds are replayed** into the replacement stream, so a
word spoken across the seam is not lost. Not more: replaying further back
would repeat sentences already on screen, and the buffer would grow with
the session.

**The replay goes out in 3,200-byte chunks.** Google rejects a request
carrying more than 25,600 bytes of audio — learned in Sprint 1 by having
one rejected, and the only places that knowledge now lives are a constant
and a test.

**It gives up after five reopens.** A recogniser that ends instantly and
repeatedly is broken, not busy, and reopening forever would hide that
behind an endless stream of nothing. Past that the session says so and
closes, which is the honest answer.

Wrapping happens in `create_stt_stream`, so `session.py` never learns any
of it happened. The mock is deliberately *not* wrapped: it ends when told
to and never early, so wrapping it would add a layer that can only pass
audio through, and would let the tests exercise a recovery that cannot
occur.

### Busy is not the same as no

The guide model is now asked again — but only when the answer was "busy".

Which is which is the **adapter's** judgement, because only it knows what
its SDK raises. `GuideModel.is_transient` defaults to False, and the
Gemini adapter overrides it: 429, 500, 503 and 504 are a service having a
moment; everything else is a decision. Retrying a request the model has
already refused spends the user's time to arrive at the same answer, and a
safety block is not a hiccup.

The whole retry budget is **1.4 seconds**, across two extra attempts.
Sprint 1 settled that a five-second delay makes this product feel broken,
and someone standing at a cash machine waiting to be told what to press
notices every second of it. A slow answer is worth having; a slow failure
is not.

Classification is by status code rather than exception class, because
google-genai raises several types across versions and all of them carry
the code.

---

## Issues

### Issue 23 — Recognition survives the end of a stream `backend-ws`
- [x] A stream that raises is replaced, not fatal
- [x] A stream that merely finishes is replaced too — the silent case
- [x] The previous stream is closed when it is replaced
- [x] The last two seconds of audio are replayed into the replacement
- [x] The replay is chunked below Google's 25,600-byte request limit
- [x] Only the recent past is replayed; the buffer does not grow with the session
- [x] Bounded at five reopens, then the session ends and says so
- [x] Closing the session does not trigger a reopen

### Issue 24 — The guide model is asked again when it was busy `backend-rest`
- [x] A transient failure is retried; the answer arrives
- [x] A refusal is not retried
- [x] Bounded at three attempts in total
- [x] The original error surfaces, not a wrapper's
- [x] The retry budget stays under two seconds
- [x] 429, 500, 503, 504 count as transient; 400, 401, 403, 404 do not
- [x] A status carried only in the message still counts
- [x] A safety block and an empty answer are not retried

### Issue 25 — The comments that promised this work `backend-ws` `backend-rest`
- [x] `stt/base.py`, `session.py` and `guide_sessions.py` describe what exists
- [x] No "Sprint 5" left in the source promising something absent

---

## Verification evidence

| Check | Evidence |
| --- | --- |
| Whole suite | 155 REST, 105 WebSocket; the widget builds clean |
| Recovery is real | Removed on purpose: four tests fail, including the silent-end case |
| Retry is real | `is_transient` bypassed on purpose: the refusal test fails |
| Recovery proved in a millisecond, not five minutes | The fake stream ends on demand, so the capped-stream case is testable without waiting for the cap |
| CI | Green on all three jobs |
| Deployed | The `Deploy` run went green; `v3` is live on Cloud Run |
| Guide mode live through the retry layer | A real Gemini answer in 3 s: "To send money, please tap on the button that says Send Money at the bottom of your screen." |
| Nothing regressed live | REST, WebSocket and widget all 200 after the deploy |

### Two test bugs of my own

An attribute named `results` on the fake stream **shadowed the `results()`
method** it existed to provide, so the wrapper ended up calling an
integer. And an opener that raised `StopIteration` when exhausted
surfaced, inside a coroutine, as `RuntimeError: coroutine raised
StopIteration` — an error that says nothing at all about recognition.

Both were fixed in the fake rather than worked around in the code under
test, which is the only version of that fix worth having. The second is a
good argument for test doubles that degrade rather than run out.

---

## Out of scope this sprint

**Beta feedback**, which §12 lists for this sprint: there are no beta
users, so there is none to incorporate. The retrospectives are what this
project has instead, and they have changed the code more than once.

Uptime checks and alerting — nothing watches the deployment, so an outage
is noticed by visiting it · Lifting the one-instance ceiling on the REST
API · Cloud SQL backups · A custom domain · Rotating the JWT signing key,
which still has no procedure where the database password now has one ·
The 106 untested language pairs, carried since Sprint 2 · Moving tokens
from `localStorage` to httpOnly cookies.
