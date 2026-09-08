import { useCallback, useEffect, useRef, useState } from "react";

import { captionSocketUrl, createCaptionSession } from "./api";
import { describeMicError, startMicCapture } from "./audio/micCapture";
import type { AudioCapture } from "./audio/pcmCapture";
import {
  describeTabAudioError,
  startTabAudioCapture,
} from "./audio/tabAudioCapture";
import { CaptionSocket, type ConnectionState } from "./ws/captionSocket";
import type { AudioSource } from "./ws/protocol";

export type SessionStatus =
  | "idle"
  | "starting"
  | "listening"
  | "reconnecting"
  | "stopping";

export interface CaptionLine {
  seq: number;
  text: string;
  isFinal: boolean;
}

// If the server never acknowledges end_stream, stop anyway rather than
// leaving the button stuck on "Finishing up".
const STREAM_END_TIMEOUT_MS = 3_000;

/** `persist` asks the server for a session row, which is what makes
 * backend-ws write the transcript down. It is false while signed out and
 * while auto-save is off: with no row there is nowhere for the words to
 * go, which is the same guarantee anonymous captioning already relies on.
 */
export function useCaptionSession(source: AudioSource, persist: boolean) {
  const [status, setStatus] = useState<SessionStatus>("idle");
  const [lines, setLines] = useState<CaptionLine[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [language, setLanguage] = useState<string | null>(null);

  const linesRef = useRef<CaptionLine[]>([]);
  // Held across a stop so that Continue reopens the same session rather
  // than starting a second one. backend-ws numbers a continued stream from
  // zero again and places it after the lines already stored, so one
  // continued recording stays one entry in the saved list.
  const sessionIdRef = useRef<string | null>(null);
  // A continued session numbers its lines from zero again, so incoming
  // captions are shifted past whatever is already on screen. Without this
  // they would merge onto the retained transcript and overwrite it.
  const seqOffsetRef = useRef(0);
  const socketRef = useRef<CaptionSocket | null>(null);
  const captureRef = useRef<AudioCapture | null>(null);
  const endTimerRef = useRef<number | null>(null);
  const statusRef = useRef<SessionStatus>("idle");

  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  useEffect(() => {
    linesRef.current = lines;
  }, [lines]);

  const teardown = useCallback(async () => {
    if (endTimerRef.current !== null) {
      window.clearTimeout(endTimerRef.current);
      endTimerRef.current = null;
    }
    await captureRef.current?.stop();
    captureRef.current = null;
    socketRef.current?.close();
    socketRef.current = null;
  }, []);

  useEffect(() => () => void teardown(), [teardown]);

  const finish = useCallback(async () => {
    await teardown();
    setStatus("idle");
  }, [teardown]);

  const handleConnectionChange = useCallback((state: ConnectionState) => {
    // Only reflect a dropped link once the session is actually running;
    // the initial connect is already covered by "starting".
    if (state === "reconnecting" && statusRef.current === "listening") {
      setStatus("reconnecting");
    } else if (state === "open" && statusRef.current === "reconnecting") {
      setStatus("listening");
    }
  }, []);

  const stop = useCallback(async () => {
    if (statusRef.current === "idle" || statusRef.current === "stopping") return;
    setStatus("stopping");
    statusRef.current = "stopping";

    await captureRef.current?.stop();
    captureRef.current = null;
    socketRef.current?.endStream();

    endTimerRef.current = window.setTimeout(() => void finish(), STREAM_END_TIMEOUT_MS);
  }, [finish]);

  /** Clears the transcript without recording, back to a fresh start. */
  const reset = useCallback(() => {
    if (statusRef.current !== "idle") return;
    sessionIdRef.current = null;
    seqOffsetRef.current = 0;
    setLines([]);
    setLanguage(null);
    setNotice(null);
  }, []);

  /** `keepTranscript` continues after what is already on screen. */
  const start = useCallback(async (keepTranscript = false) => {
    if (statusRef.current !== "idle") return;
    setNotice(null);
    if (keepTranscript) {
      seqOffsetRef.current = nextSeq(linesRef.current);
    } else {
      sessionIdRef.current = null;
      seqOffsetRef.current = 0;
      setLines([]);
    }
    setLanguage(null);
    setStatus("starting");
    statusRef.current = "starting";

    try {
      const sessionId =
        (keepTranscript ? sessionIdRef.current : null) ?? (await openSession(source, persist));
      sessionIdRef.current = sessionId;
      const socket = new CaptionSocket(captionSocketUrl(sessionId), source, {
        onCaption: (caption) => {
          const seq = caption.seq + seqOffsetRef.current;
          setLines((previous) => mergeLine(previous, seq, caption.text, caption.is_final));
          if (caption.language) setLanguage(caption.language);
        },
        onError: (message) => setNotice(message),
        onStreamEnded: () => void finish(),
        onConnectionChange: handleConnectionChange,
      });
      socketRef.current = socket;
      await socket.open();

      const send = (pcm: ArrayBuffer) => socket.sendAudioChunk(pcm);
      try {
        captureRef.current =
          source === "mic"
            ? await startMicCapture(send)
            : await startTabAudioCapture(send, () => {
                // Sharing was stopped from the browser's own bar, so there
                // is nothing left to caption. Finish rather than sit silent.
                setNotice("Sharing stopped, so captioning has finished.");
                void stop();
              });
      } catch (error) {
        throw new Error(
          source === "mic" ? describeMicError(error) : describeTabAudioError(error),
        );
      }

      setStatus("listening");
      statusRef.current = "listening";
    } catch (error) {
      await teardown();
      setStatus("idle");
      statusRef.current = "idle";
      setNotice(error instanceof Error ? error.message : "Could not start captions.");
    }
  }, [finish, handleConnectionChange, persist, source, stop, teardown]);

  return {
    status,
    lines,
    notice,
    language,
    reset,
    start,
    stop,
    dismissNotice: useCallback(() => setNotice(null), []),
  };
}

/** An id to key the stream by, and a row behind it only when asked.
 *
 * Without a row backend-ws finds nothing and writes nothing, so an id made
 * here is how "do not save this" is expressed -- no request field says it,
 * and none can be forgotten.
 */
async function openSession(source: AudioSource, persist: boolean): Promise<string> {
  return persist ? await createCaptionSession(source) : crypto.randomUUID();
}

/** The seq a continued session should start from, so it appends. */
export function nextSeq(lines: CaptionLine[]): number {
  return lines.length === 0 ? 0 : Math.max(...lines.map((line) => line.seq)) + 1;
}

/** Replaces the line with this seq, so interim text is revised in place. */
export function mergeLine(
  lines: CaptionLine[],
  seq: number,
  text: string,
  isFinal: boolean,
): CaptionLine[] {
  const next = lines.filter((line) => line.seq !== seq);
  next.push({ seq, text, isFinal });
  next.sort((a, b) => a.seq - b.seq);
  return next;
}
