// Where the tokens live between page loads.
//
// localStorage rather than an httpOnly cookie, matching how the API hands
// them out. It is reachable from JavaScript, which is the known cost;
// moving both sides to a cookie is the hardening if this ever leaves a
// portfolio.

const ACCESS = "wayfinder.access_token";
const REFRESH = "wayfinder.refresh_token";

export interface StoredTokens {
  access_token: string;
  refresh_token: string;
}

/** Kept in memory as well, so a request never waits on storage. */
let accessToken: string | null = null;

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    // Private windows and blocked site data both throw here. Signing in
    // still works for this tab; it just will not be remembered.
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // Nothing to do: the session simply lasts as long as the tab does.
  }
}

export function loadTokens(): StoredTokens | null {
  const access = read(ACCESS);
  const refresh = read(REFRESH);
  accessToken = access;
  if (!access || !refresh) return null;
  return { access_token: access, refresh_token: refresh };
}

export function saveTokens(tokens: StoredTokens): void {
  accessToken = tokens.access_token;
  write(ACCESS, tokens.access_token);
  write(REFRESH, tokens.refresh_token);
}

export function clearTokens(): void {
  accessToken = null;
  write(ACCESS, null);
  write(REFRESH, null);
}

export function refreshToken(): string | null {
  return read(REFRESH);
}

/** The Authorization header, or nothing while signed out. */
export function authHeaders(): Record<string, string> {
  return accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
}
