// The /api/auth and /api/users endpoints from Plan.md section 4.

import { REST_BASE } from "../api";
import { authHeaders, type StoredTokens } from "./session";

export interface Account {
  id: string;
  email: string;
  display_name: string;
  font_size: number;
  caption_language: string | null;
}

async function readError(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    // A validation failure comes back as a list; the first message is the
    // useful one and the rest repeat it for other fields.
    if (Array.isArray(body.detail) && body.detail.length > 0) {
      const first = body.detail[0] as { msg?: unknown };
      if (typeof first.msg === "string") return first.msg;
    }
  } catch {
    // A non-JSON error body is not worth surfacing over the fallback.
  }
  return fallback;
}

async function post(path: string, body: unknown, fallback: string): Promise<StoredTokens> {
  const response = await fetch(`${REST_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await readError(response, fallback));
  return (await response.json()) as StoredTokens;
}

export function signUp(
  email: string,
  password: string,
  displayName: string,
): Promise<StoredTokens> {
  return post(
    "/api/auth/signup",
    { email, password, display_name: displayName },
    "Could not create the account.",
  );
}

export function signIn(email: string, password: string): Promise<StoredTokens> {
  return post("/api/auth/login", { email, password }, "Could not sign in.");
}

export function renew(token: string): Promise<StoredTokens> {
  return post("/api/auth/refresh", { refresh_token: token }, "Session expired.");
}

export async function signOut(token: string): Promise<void> {
  // Best effort: the tokens are cleared locally either way, so a failure
  // here must not leave someone stuck looking signed in.
  await fetch(`${REST_BASE}/api/auth/logout`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ refresh_token: token }),
  }).catch(() => undefined);
}

export async function fetchAccount(): Promise<Account> {
  const response = await fetch(`${REST_BASE}/api/users/me`, {
    headers: authHeaders(),
  });
  if (!response.ok) throw new Error(await readError(response, "Could not load your account."));
  return (await response.json()) as Account;
}

export async function saveFontSize(fontSize: number): Promise<Account> {
  const response = await fetch(`${REST_BASE}/api/users/me`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ font_size: fontSize }),
  });
  if (!response.ok) throw new Error(await readError(response, "Could not save that setting."));
  return (await response.json()) as Account;
}
