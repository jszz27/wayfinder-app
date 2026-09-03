import { useCallback, useEffect, useRef, useState } from "react";

import { captionSocketUrl, createCaptionSession } from "./api";
import {
  describeMicError,
  startMicCapture,
  type MicCapture,
} from "./audio/micCapture";
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

export function useCaptionSession(source: AudioSource) {
  const [status, setStatus] = useState<SessionStatus>("idle");
  const [lines, setLines] = useState<CaptionLine[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [language, setLanguage] = useState<string | null>(null);

  const socketRef = useRef<CaptionSocket | null>(null);
  const captureRef = useRef<MicCapture | null>(null);
  const endTimerRef = useRef<number | null>(null);
  const statusRef = useRef<SessionStatus>("idle");

  useEffect(() => {
    statusRef.current = status;
  }, [status]);

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

  const start = useCallback(async () => {
    if (statusRef.current !== "idle") return;
    setNotice(null);
    setLines([]);
    setLanguage(null);
    setStatus("starting");
    statusRef.current = "starting";

    try {
      const sessionId = await createCaptionSession(source);
      const socket = new CaptionSocket(captionSocketUrl(sessionId), source, {
        onCaption: (caption) => {
          setLines((previous) => mergeLine(previous, caption.seq, caption.text, caption.is_final));
          if (caption.language) setLanguage(caption.language);
        },
        onError: (message) => setNotice(message),
        onStreamEnded: () => void finish(),
        onConnectionChange: handleConnectionChange,
      });
      socketRef.current = socket;
      await socket.open();

      try {
        captureRef.current = await startMicCapture((pcm) => socket.sendAudioChunk(pcm));
      } catch (error) {
        throw new Error(describeMicError(error));
      }

      setStatus("listening");
      statusRef.current = "listening";
    } catch (error) {
      await teardown();
      setStatus("idle");
      statusRef.current = "idle";
      setNotice(error instanceof Error ? error.message : "Could not start captions.");
    }
  }, [finish, handleConnectionChange, source, teardown]);

  const stop = useCallback(async () => {
    if (statusRef.current === "idle" || statusRef.current === "stopping") return;
    setStatus("stopping");
    statusRef.current = "stopping";

    await captureRef.current?.stop();
    captureRef.current = null;
    socketRef.current?.endStream();

    endTimerRef.current = window.setTimeout(() => void finish(), STREAM_END_TIMEOUT_MS);
  }, [finish]);

  return {
    status,
    lines,
    notice,
    language,
    start,
    stop,
    dismissNotice: useCallback(() => setNotice(null), []),
  };
}

/** Replaces the line with this seq, so interim text is revised in place. */
function mergeLine(
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
