import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchAccount,
  renew,
  saveSettings,
  signIn as signInRequest,
  signOut as signOutRequest,
  signUp as signUpRequest,
  type Account,
  type SettingsPatch,
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

  /** Runs one request, reporting its failure rather than throwing it. */
  const attempt = useCallback(async (work: () => Promise<void>) => {
    setNotice(null);
    setBusy(true);
    try {
      await work();
      return true;
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "That did not work.");
      return false;
    } finally {
      setBusy(false);
    }
  }, []);

  const signIn = useCallback(
    (email: string, password: string) =>
      attempt(async () => adopt(await signInRequest(email, password))),
    [adopt, attempt],
  );

  // Creating an account does not sign anyone in; the sign in page is where
  // that happens, and where the new password gets used for the first time.
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

  const remember = useCallback(
    async (patch: SettingsPatch) => {
      if (status !== "signed-in") return;
      try {
        setAccount(await saveSettings(patch));
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
    rememberFontSize: useCallback(
      (fontSize: number) => remember({ font_size: fontSize }),
      [remember],
    ),
    rememberAutoSave: useCallback(
      (autoSave: boolean) => remember({ auto_save: autoSave }),
      [remember],
    ),
    dismissNotice: useCallback(() => setNotice(null), []),
  };
}
