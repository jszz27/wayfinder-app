// The /api/guide/* endpoints from Plan.md section 4. This file mirrors
// backend-rest/app/routers/guide_sessions.py field for field.

import { REST_BASE } from "../api";
import { authHeaders } from "../auth/session";

export type GuideRole = "user" | "assistant";

export interface GuideMessage {
  id: string;
  role: GuideRole;
  content: string;
  created_at: string;
}

export interface GuideSession {
  id: string;
  started_at: string;
  completed_at: string | null;
  messages: GuideMessage[];
}

async function readError(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // A non-JSON error body is not worth surfacing over the fallback.
  }
  return fallback;
}

export async function createGuideSession(): Promise<string> {
  const response = await fetch(`${REST_BASE}/api/guide/sessions`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new Error(
      await readError(response, "Could not start the guide. Check the server is running."),
    );
  }
  const body = (await response.json()) as { session_id?: unknown };
  if (typeof body.session_id !== "string") {
    throw new Error("The server did not return valid session details.");
  }
  return body.session_id;
}

export async function sendGuideMessage(
  sessionId: string,
  content: string,
  screenshot: string | null,
): Promise<GuideMessage> {
  const response = await fetch(
    `${REST_BASE}/api/guide/sessions/${encodeURIComponent(sessionId)}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      // `screenshot` is sent only while screen sharing is on, per
      // Plan.md section 10 -- omitted entirely otherwise.
      body: JSON.stringify(screenshot === null ? { content } : { content, screenshot }),
    },
  );
  if (!response.ok) {
    throw new Error(await readError(response, "The guide could not answer. Try again."));
  }
  return (await response.json()) as GuideMessage;
}

export async function completeGuideSession(sessionId: string): Promise<GuideSession> {
  const response = await fetch(
    `${REST_BASE}/api/guide/sessions/${encodeURIComponent(sessionId)}/complete`,
    { method: "PATCH", headers: authHeaders() },
  );
  if (!response.ok) {
    throw new Error(await readError(response, "Could not finish the session."));
  }
  return (await response.json()) as GuideSession;
}

export async function getGuideSession(sessionId: string): Promise<GuideSession> {
  const response = await fetch(
    `${REST_BASE}/api/guide/sessions/${encodeURIComponent(sessionId)}`,
    { headers: authHeaders() },
  );
  if (!response.ok) {
    throw new Error(await readError(response, "Could not load the conversation."));
  }
  return (await response.json()) as GuideSession;
}
