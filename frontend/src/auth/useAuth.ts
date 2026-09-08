import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchAccount,
  renew,
  saveFontSize,
  signIn as signInRequest,
  signOut as signOutRequest,
  signUp as signUpRequest,
  type Account,
} from "./api";
import {
  clearTokens,
  loadTokens,
  refreshToken,
  saveTokens,
  type StoredTokens,
} from "./session";

export type AuthStatus = "loading" | "signed-out" | "signed-in";

export function useAuth() {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [account, setAccount] = useState<Account | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const startedRef = useRef(false);

  const adopt = useCallback(async (tokens: StoredTokens) => {
    saveTokens(tokens);
    setAccount(await fetchAccount());
    setStatus("signed-in");
  }, []);

  const forget = useCallback(() => {
    clearTokens();
    setAccount(null);
    setStatus("signed-out");
  }, []);

  // A stored session is resumed on load. The access token has almost
  // certainly expired -- they last fifteen minutes -- so the refresh token
  // is what is actually worth anything here.
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    const stored = loadTokens();
    const token = stored?.refresh_token ?? refreshToken();
    if (!token) {
      setStatus("signed-out");
      return;
    }
    void (async () => {
      try {
        await adopt(await renew(token));
      } catch {
        // An expired or revoked session is not an error worth showing:
        // from the user's side they were simply signed out.
        forget();
      }
    })();
  }, [adopt, forget]);

  const attempt = useCallback(
    async (work: () => Promise<StoredTokens>) => {
      setNotice(null);
      setBusy(true);
      try {
        await adopt(await work());
        return true;
      } catch (error) {
        setNotice(error instanceof Error ? error.message : "That did not work.");
        return false;
      } finally {
        setBusy(false);
      }
    },
    [adopt],
  );

  const signIn = useCallback(
    (email: string, password: string) => attempt(() => signInRequest(email, password)),
    [attempt],
  );

  const signUp = useCallback(
    (email: string, password: string, displayName: string) =>
      attempt(() => signUpRequest(email, password, displayName)),
    [attempt],
  );

  const signOut = useCallback(async () => {
    const token = refreshToken();
    // Cleared first, so a failing request cannot leave someone looking
    // signed in when they have asked not to be.
    forget();
    if (token) await signOutRequest(token);
  }, [forget]);

  const rememberFontSize = useCallback(
    async (fontSize: number) => {
      if (status !== "signed-in") return;
      try {
        setAccount(await saveFontSize(fontSize));
      } catch {
        // A setting that did not save is not worth interrupting for; it
        // still applies to this tab.
      }
    },
    [status],
  );

  return {
    status,
    account,
    notice,
    busy,
    signIn,
    signUp,
    signOut,
    rememberFontSize,
    dismissNotice: useCallback(() => setNotice(null), []),
  };
}
