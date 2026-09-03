import { useCallback, useEffect, useRef, useState } from "react";

import {
  completeGuideSession,
  createGuideSession,
  sendGuideMessage,
  type GuideMessage,
} from "./api";
import {
  describeScreenError,
  startScreenShare,
  type ScreenShare,
} from "../screen/screenCapture";

export type GuideStatus = "idle" | "sending" | "complete";

export function useGuideSession() {
  const [messages, setMessages] = useState<GuideMessage[]>([]);
  const [status, setStatus] = useState<GuideStatus>("idle");
  const [notice, setNotice] = useState<string | null>(null);
  const [sharing, setSharing] = useState(false);

  const sessionRef = useRef<string | null>(null);
  const shareRef = useRef<ScreenShare | null>(null);

  const stopSharing = useCallback(() => {
    shareRef.current?.stop();
    shareRef.current = null;
    setSharing(false);
  }, []);

  useEffect(() => () => shareRef.current?.stop(), []);

  const startSharing = useCallback(async () => {
    setNotice(null);
    try {
      shareRef.current = await startScreenShare(() => {
        // Stopped from the browser's own sharing bar, not our pill.
        shareRef.current = null;
        setSharing(false);
      });
      setSharing(true);
    } catch (error) {
      setNotice(describeScreenError(error));
      setSharing(false);
    }
  }, []);

  const send = useCallback(async (text: string) => {
    const content = text.trim();
    if (!content || status === "sending" || status === "complete") return;

    setNotice(null);
    setStatus("sending");

    // Shown straight away so the question does not vanish while waiting;
    // the server assigns the real id, which arrives with the reply.
    const pending: GuideMessage = {
      id: `pending-${Date.now()}`,
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((previous) => [...previous, pending]);

    try {
      if (sessionRef.current === null) {
        sessionRef.current = await createGuideSession();
      }
      // Captured at the moment of sending, never before (Plan.md section 10).
      const screenshot = shareRef.current?.capture() ?? null;
      const reply = await sendGuideMessage(sessionRef.current, content, screenshot);
      setMessages((previous) => [...previous, reply]);
      setStatus("idle");
    } catch (error) {
      setMessages((previous) => previous.filter((m) => m.id !== pending.id));
      setNotice(error instanceof Error ? error.message : "The guide could not answer.");
      setStatus("idle");
    }
  }, [status]);

  const finish = useCallback(async () => {
    if (sessionRef.current === null || status === "sending") return;
    try {
      await completeGuideSession(sessionRef.current);
      setStatus("complete");
      stopSharing();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not finish the session.");
    }
  }, [status, stopSharing]);

  const reset = useCallback(() => {
    sessionRef.current = null;
    setMessages([]);
    setStatus("idle");
    setNotice(null);
  }, []);

  return {
    messages,
    status,
    notice,
    sharing,
    hasSession: sessionRef.current !== null || messages.length > 0,
    send,
    finish,
    reset,
    startSharing,
    stopSharing,
    dismissNotice: useCallback(() => setNotice(null), []),
  };
}
