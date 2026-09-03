# Sprint 1 — WebSocket caption MVP

**Goal** (`Plan.md` §7 Step 1, §12): a minimal, fully working path from
mic input → WebSocket server → STT → caption text on screen.

**Board columns**: `Backlog` → `To do` → `In progress` → `In review` → `Done`

---

## Protocol agreements

The WebSocket messages are exactly the five in `Plan.md` §5 — no fields
added, renamed, or dropped. Two points that §5 leaves open are settled
here rather than in code comments.

### `caption.seq` means "caption line number"

§5 uses `42` as the example value for both `audio_chunk.seq` and
`caption.seq`, which reads two ways. We take it as the caption **line**
ordinal, matching `caption_lines(session_id, seq, text)` in §6 — a
streaming STT result spans many audio chunks, so echoing a chunk seq
would not be well defined.

The server keeps a per-session counter. Every interim result for the
utterance being formed carries the same `seq`; the counter increments
once `is_final: true` has been sent for that line. The widget therefore
replaces a line in place by `seq`, which is what §8's "latest confirmed
line bold, earlier lines faded" needs.

### Audio wire format

§5 only says `"data": "<base64>"`. The agreed encoding is:

| | |
|---|---|
| Sample rate | 16 000 Hz |
| Channels | 1 (mono) |
| Sample format | signed 16-bit little-endian PCM (LINEAR16) |
| Chunk size | ~100 ms = 1 600 samples = 3 200 bytes |
| Transport | those 3 200 bytes, base64-encoded, in `data` |

### Deferred: caption language

§4's `caption_sessions.language` has no route to the WebSocket server in
the §5 message set, so Sprint 1 fixes the language server-side via
`STT_LANGUAGE` (default `ko-KR`) and the §8 settings bar exposes font
size only. The language selector lands in Sprint 3 together with the
session API.

> **Superseded after Sprint 1.** Rather than a selector, the language is
> now detected automatically, and `caption.language` was added to §5 to
> report it -- the one field added since. The §5 message set is otherwise
> still frozen, and `SPEC_FIELDS` in `tests/test_caption_ws.py` keeps it
> that way.

---

## Issues

### Issue 0 — Repository skeleton `infra`
- [x] Three-service directory layout (`frontend/`, `backend-ws/`, `backend-rest/`)
- [x] `.gitignore` covering Python, Node, and credential files
- [x] `.env.example` documenting every variable the three services read
- [x] Root `README.md` mapping each folder to a `Plan.md` §3 component
- [x] Each service starts after installing its own dependencies

### Issue 1 — REST server skeleton `backend-rest`
- [x] `GET /health` returns `{"status": "ok"}`
- [x] `POST /api/caption-sessions` with body `{"audio_source": "mic"}` (§4) returns a `session_id`
- [x] An invalid `audio_source` is rejected with 422
- [x] Sessions held in memory — no database this sprint
- [x] CORS allows the widget's dev origin
- [x] `pytest` covers all of the above

### Issue 2 — WebSocket server skeleton `backend-ws`
- [x] `GET /health` returns `{"status": "ok"}`
- [x] `WS /ws/caption?session_id=...` accepts a connection
- [x] A missing `session_id` closes the socket with code 1008
- [x] The five §5 messages are modelled once, in `app/protocol.py`
- [x] An unknown message `type` replies with `error` and keeps the connection open
- [x] Mock STT adapter (`WAYFINDER_STT=mock`) produces interim then final captions
- [x] `end_stream` flushes the last final caption, sends `stream_ended`, then closes
- [x] `pytest` covers the full round trip against the mock adapter

### Issue 3 — STT API integration `backend-ws`
- [x] `SttStream` interface: `push(pcm)`, `results()`, `close()`
- [x] Google Cloud STT v2 streaming adapter, LINEAR16 / 16 kHz / mono, `interim_results=True`
- [x] Receive loop and STT consume loop are decoupled by a per-session queue
- [x] `caption.seq` follows the line-counter rule above
- [x] An STT failure sends one `error` message, then closes (retry/fallback is Sprint 5)
- [x] Real speech produces captions with `WAYFINDER_STT=google`
- [x] Mock-path tests still pass

### Issue 4 — Mic input → send `frontend`
- [x] `getUserMedia({audio: true})` capture at 16 kHz mono, with a resample fallback
- [x] Float32 → PCM16 conversion in an AudioWorklet, off the main thread
- [x] Start requests a `session_id` from the REST server, then opens the WebSocket
- [x] Chunks sent as `audio_chunk` with a monotonically increasing `seq`
- [x] `source` is fixed to `"mic"` for the whole session (§5)
- [x] Stop sends `end_stream` and waits for `stream_ended`
- [x] A dropped connection reconnects within 5 seconds (exponential backoff)
- [x] A denied mic permission surfaces a readable message, not a console error

### Issue 5 — Caption UI in the widget `frontend`
- [x] Caption / guide **tabs** on top; guide is a Sprint 2 placeholder
- [x] Below them, a muted "source" label plus a small pill segmented control (§8)
- [x] "Playing audio" segment is present but disabled, with a note that it lands later
- [x] Status line reflects the selection ("마이크로 듣는 중…")
- [x] Lines are replaced in place by `seq`; latest confirmed line bold, earlier lines faded
- [x] Interim text is visually distinct from confirmed text
- [x] Caption area auto-scrolls as lines arrive
- [x] Font size setting at the bottom changes the caption text size

---

---

## Verification evidence

Recorded at sprint end so the checkboxes above are traceable.

| Check | Evidence |
|---|---|
| REST endpoints | `pytest` in `backend-rest`: 8 passed |
| WebSocket protocol, mock STT, recogniser failure | `pytest` in `backend-ws`: 18 passed |
| Live socket, no browser | `tests/manual_client.py` against a running server: interim/interim/final per line, `seq` 0,1,2,…, `stream_ended` on close |
| Caption text is intact UTF-8 | Codepoints on the wire read `U+C624 U+B298` ("오늘"), so mojibake in a Windows console is a terminal codepage artifact only |
| Widget end to end | Chrome: `POST /api/caption-sessions` 201 → WebSocket accepted → captions rendered, latest confirmed line bold, interim italic, auto-scrolled |
| Client sends only spec fields | Frames captured in-page: 21 `audio_chunk`s, `seq` 0→20 strictly monotonic, `source` only ever `"mic"`, keys exactly `data,seq,source,type`, final frame `end_stream` |
| Audio wire format | Each captured chunk base64-decodes to exactly 3200 bytes = 100 ms of 16 kHz mono PCM16 |
| Reconnect within 5 s | Killed `backend-ws` mid-stream: status became "연결이 끊겨 다시 연결하는 중…", server restarted, client reconnected with the same `session_id` and returned to "마이크로 듣는 중…" |
| Stop path | `end_stream` flushed the open interim line into a confirmed line, then the UI returned to idle |
| Denied microphone | `getUserMedia` stubbed to reject with `NotAllowedError`: readable message shown in a `role="alert"` region, UI back to idle |
| Font size setting | Caption panel computed size stepped 16 → 20 → 26 → 34 px |
| Google adapter against the real SDK | `pip install ".[google]"`, then every symbol `google_v2.py` uses constructed offline: `ExplicitDecodingConfig` at LINEAR16 / 16 000 Hz / 1 channel, `interim_results=True`, both `StreamingRecognizeRequest` forms, and the `results` → `alternatives[0].transcript` / `is_final` read path. `SpeechAsyncClient.streaming_recognize(requests=…)` signature matches the call site |
| `WAYFINDER_STT=google` selection path | `create_stt_stream()` returns `GoogleSttStream`; an unset `GOOGLE_CLOUD_PROJECT` raises before any network call |
| Mock path unaffected by the new dependency | `pytest` in `backend-ws`: 18 passed; `pip check`: no broken requirements |
| Live credentials | Organization policy `iam.disableServiceAccountKeyCreation` blocks service-account keys, so Application Default Credentials are used instead (`gcloud auth application-default login` plus a quota project). No key file exists |
| Real speech, real service | A 33 s Korean session against `WAYFINDER_STT=google`: interim lines revised in place and finalised, `caption.seq` behaving as specified. The Speech API's enablement is proven by the absence of a `403` |
| `uvicorn --env-file` actually applies | The same silent WAV yields no captions on port 8001 (`--env-file ../.env`, Google) and scripted captions on port 8002 (mock). Nothing in the app auto-loaded `.env` at the time, so the flag was required. Superseded in Sprint 2: both services now read `.env` themselves and the flag is optional |

**Every acceptance criterion is met.** The two that had been blocked on
credentials are closed: the adapter is exercised against the installed SDK,
and real Korean speech has been transcribed through the live service.

The risk this sprint carried longest — whether Google's real interim results
would segment sensibly against the `caption.seq` line rule agreed above —
did not materialise. Lines were revised in place and finalised as specified.

One defect surfaced only under live conditions and is fixed: long sentences
made the whole widget jump sideways. `body` is a flex container and `#root`
had no width of its own, so it took its max-content size and the widget's
`min(560px, 100%)` resolved against a width that tracked the longest caption
line. Every interim result resized the widget between 276 px and 474 px, and
`justify-content: center` turned each resize into a horizontal jump. Giving
`#root` a definite width fixes it. Notably this was invisible to the mock
adapter, whose caption lines are a fixed length — only variable-length real
speech crossed the threshold.

## Out of scope this sprint

Guide mode, LLM, TTS (§10, Sprint 2) · auth, JWT, session log retrieval
(§4, Sprint 3) · PostgreSQL and `caption_lines` persistence (§6, Sprint 3)
· GitHub Actions and Cloud Run deployment (Sprint 4) · STT retry and
fallback (Sprint 5) · `tab_audio` capture (§9 — the pill control ships
disabled).
