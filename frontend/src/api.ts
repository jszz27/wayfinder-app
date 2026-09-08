import { authHeaders } from "./auth/session";
import type { AudioSource } from "./ws/protocol";

// Empty base means same-origin, which the Vite dev proxy forwards to the
// two backend services. Override per environment if they are hosted apart.
export const REST_BASE = import.meta.env.VITE_REST_BASE_URL ?? "";

export async function createCaptionSession(
  audioSource: AudioSource,
): Promise<string> {
  const response = await fetch(`${REST_BASE}/api/caption-sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ audio_source: audioSource }),
  });
  if (!response.ok) {
    throw new Error("Could not start a caption session. Check that the server is running.");
  }
  const body = (await response.json()) as { session_id?: unknown };
  if (typeof body.session_id !== "string") {
    throw new Error("The server did not return valid session details.");
  }
  return body.session_id;
}

export function captionSocketUrl(sessionId: string): string {
  const fallback = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}`;
  const base = import.meta.env.VITE_WS_BASE_URL ?? fallback;
  return `${base}/ws/caption?session_id=${encodeURIComponent(sessionId)}`;
}
