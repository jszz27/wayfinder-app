// The /api/caption-sessions endpoints from Plan.md section 4, plus the two
// added in Sprint 3 for keeping and correcting a transcript (docs/sprint-3.md).

import { REST_BASE } from "../api";
import { authHeaders } from "../auth/session";
import type { AudioSource } from "../ws/protocol";

export interface SavedSession {
  id: string;
  started_at: string;
  ended_at: string | null;
  language: string | null;
  audio_source: AudioSource;
  /** Null until it is named; the list shows the date instead. */
  title: string | null;
  /** True once the text has been corrected or saved by hand. */
  edited: boolean;
}

export interface SavedSessionDetail extends SavedSession {
  /** What to show: the kept text, or the recognised lines joined. */
  text: string;
  lines: { seq: number; text: string; created_at: string }[];
}

async function request<T>(
  path: string,
  init: RequestInit,
  fallback: string,
): Promise<T> {
  const response = await fetch(`${REST_BASE}${path}`, {
    ...init,
    headers: { ...(init.headers ?? {}), ...authHeaders() },
  });
  if (!response.ok) {
    let detail: string | null = null;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // A non-JSON error body is not worth surfacing over the fallback.
    }
    throw new Error(detail ?? fallback);
  }
  // 204, which delete answers with.
  return (response.status === 204 ? undefined : await response.json()) as T;
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function listSessions(): Promise<SavedSession[]> {
  return request("/api/caption-sessions", {}, "Could not load your saved text.");
}

export function getSession(id: string): Promise<SavedSessionDetail> {
  return request(`/api/caption-sessions/${id}`, {}, "Could not open that session.");
}

export function renameSession(id: string, title: string): Promise<SavedSession> {
  return request(
    `/api/caption-sessions/${id}`,
    json("PATCH", { title }),
    "Could not rename that session.",
  );
}

export function saveSessionText(id: string, text: string): Promise<SavedSession> {
  return request(
    `/api/caption-sessions/${id}`,
    json("PATCH", { text }),
    "Could not save your changes.",
  );
}

export function deleteSession(id: string): Promise<void> {
  return request(
    `/api/caption-sessions/${id}`,
    { method: "DELETE" },
    "Could not delete that session.",
  );
}

/** Keeps a transcript the widget was holding, for when auto-save is off. */
export function saveTranscript(
  audioSource: AudioSource,
  text: string,
): Promise<SavedSession> {
  return request(
    "/api/caption-sessions/saved",
    json("POST", { audio_source: audioSource, text }),
    "Could not save this text.",
  );
}
