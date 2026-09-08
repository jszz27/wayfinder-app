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

/** `keep` decides whether this conversation belongs to the account.
 *
 * False sends no token, so the server holds the conversation in its own
 * process and writes nothing -- the same path an anonymous conversation
 * takes. It has to be held somewhere, unlike a caption transcript, because
 * the model needs the earlier turns to answer a follow-up.
 */
export async function createGuideSession(keep: boolean): Promise<string> {
  const response = await fetch(`${REST_BASE}/api/guide/sessions`, {
    method: "POST",
    headers: keep ? authHeaders() : {},
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
  keep = true,
): Promise<GuideMessage> {
  const response = await fetch(
    `${REST_BASE}/api/guide/sessions/${encodeURIComponent(sessionId)}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(keep ? authHeaders() : {}) },
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

// --- reading conversations back ---------------------------------------
//
// `GET /api/guide/sessions` is not in Plan.md section 4 as written; it was
// added in Sprint 3, because until then a signed-in user's conversations
// were stored and unreachable.

export interface SavedConversation {
  id: string;
  started_at: string;
  completed_at: string | null;
  /** Null until renamed; the opening question is shown instead. */
  title: string | null;
  /** The first thing they asked, which is what makes one recognisable. */
  opening: string | null;
  exchanges: number;
}

export async function listConversations(): Promise<SavedConversation[]> {
  const response = await fetch(`${REST_BASE}/api/guide/sessions`, {
    headers: authHeaders(),
  });
  if (!response.ok) throw new Error("Could not load your conversations.");
  return (await response.json()) as SavedConversation[];
}

/** Keeps a conversation that was not being kept (auto-save off).
 *
 * The server writes its own copy of the exchange, not one sent from here,
 * so nothing can be put in the assistant's mouth by asking for it to be
 * saved. Calling it again after carrying on adds the turns since.
 */
export async function saveGuideSession(
  sessionId: string,
): Promise<SavedConversation> {
  const response = await fetch(
    `${REST_BASE}/api/guide/sessions/${encodeURIComponent(sessionId)}/save`,
    { method: "POST", headers: authHeaders() },
  );
  if (!response.ok) {
    throw new Error(await readError(response, "Could not save this conversation."));
  }
  return (await response.json()) as SavedConversation;
}

export async function renameConversation(
  id: string,
  title: string,
): Promise<SavedConversation> {
  const response = await fetch(`${REST_BASE}/api/guide/sessions/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) {
    throw new Error(await readError(response, "Could not rename that conversation."));
  }
  return (await response.json()) as SavedConversation;
}

export async function deleteConversation(id: string): Promise<void> {
  const response = await fetch(`${REST_BASE}/api/guide/sessions/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new Error(await readError(response, "Could not delete that conversation."));
  }
}
