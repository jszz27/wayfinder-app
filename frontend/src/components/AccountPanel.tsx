import { useState } from "react";

import type { Account, AuthStatus } from "../auth/useAuth.types";

interface AccountPanelProps {
  status: AuthStatus;
  account: Account | null;
  notice: string | null;
  busy: boolean;
  onSignIn: (email: string, password: string) => Promise<boolean>;
  onSignUp: (email: string, password: string, name: string) => Promise<boolean>;
  onSignOut: () => void;
  onDismissNotice: () => void;
}

// Plan.md section 8 keeps the widget to one screen with no routing, so
// signing in is a panel that opens in place rather than a page of its own.
// It sits by the settings, because that is what an account is for here:
// keeping your text size and your transcripts, not getting in.
export function AccountPanel({
  status,
  account,
  notice,
  busy,
  onSignIn,
  onSignUp,
  onSignOut,
  onDismissNotice,
}: AccountPanelProps) {
  const [open, setOpen] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");

  if (status === "loading") {
    return <span className="account-status">Checking your account&hellip;</span>;
  }

  if (status === "signed-in" && account) {
    return (
      <div className="account-row">
        <span className="account-status">
          Signed in as <strong>{account.display_name}</strong>. Captions are being saved.
        </span>
        <button type="button" className="account-link" onClick={onSignOut}>
          Sign out
        </button>
      </div>
    );
  }

  const submit = async () => {
    const ok = registering
      ? await onSignUp(email.trim(), password, name.trim())
      : await onSignIn(email.trim(), password);
    if (ok) {
      setOpen(false);
      setPassword("");
    }
  };

  return (
    <div className="account">
      <div className="account-row">
        <span className="account-status">
          Not signed in, so nothing is being saved.
        </span>
        <button
          type="button"
          className="account-link"
          aria-expanded={open}
          onClick={() => {
            setOpen(!open);
            onDismissNotice();
          }}
        >
          {open ? "Close" : "Sign in"}
        </button>
      </div>

      {open && (
        <form
          className="account-panel"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          {registering && (
            <label className="account-field">
              <span>Your name</span>
              <input
                type="text"
                autoComplete="name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />
            </label>
          )}
          <label className="account-field">
            <span>Email</span>
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label className="account-field">
            <span>Password</span>
            <input
              type="password"
              autoComplete={registering ? "new-password" : "current-password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={registering ? 10 : 1}
            />
          </label>

          {notice && (
            <p className="account-notice" role="alert">
              {notice}
            </p>
          )}

          <div className="account-actions">
            <button
              type="button"
              className="account-link"
              onClick={() => {
                setRegistering(!registering);
                onDismissNotice();
              }}
            >
              {registering ? "I already have an account" : "Create an account"}
            </button>
            <button type="submit" className="primary-button account-submit" disabled={busy}>
              {busy ? "Working" : registering ? "Create account" : "Sign in"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
