import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAccount } from "../auth/AuthProvider";

interface ArrivedFrom {
  /** Set by the sign up page, so a new account lands here explained. */
  created?: boolean;
}

export function SignInPage() {
  const { status, notice, busy, signIn, dismissNotice } = useAccount();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  if (status === "signed-in") return <Navigate to="/" replace />;

  const created = (location.state as ArrivedFrom | null)?.created === true;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (await signIn(email.trim(), password)) navigate("/", { replace: true });
  };

  return (
    <div className="page">
      <h1 className="page-title">Sign in</h1>
      {created ? (
        <p className="page-lead">
          Your account is ready. Sign in and your text will be kept.
        </p>
      ) : (
        <p className="page-lead">
          An account keeps your text size and the text you record.
        </p>
      )}

      <form className="account-panel" onSubmit={(event) => void submit(event)}>
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
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>

        {notice && (
          <p className="account-notice" role="alert">
            {notice}
          </p>
        )}

        <div className="account-actions">
          <Link className="account-link" to="/signup" onClick={dismissNotice}>
            Create an account
          </Link>
          <button type="submit" className="primary-button account-submit" disabled={busy}>
            {busy ? "Working" : "Sign in"}
          </button>
        </div>
      </form>
    </div>
  );
}
