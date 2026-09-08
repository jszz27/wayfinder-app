import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { useAccount } from "../auth/AuthProvider";

const MIN_PASSWORD = 10;
const MISMATCH = "Those two passwords are not the same.";

export function SignUpPage() {
  const { status, notice, busy, signUp, dismissNotice } = useAccount();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [mismatch, setMismatch] = useState(false);

  if (status === "signed-in") return <Navigate to="/" replace />;

  // Only once there is something to compare: complaining while someone is
  // still typing the second password is noise, not help.
  const mismatchNow = confirmation.length > 0 && confirmation !== password;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (password !== confirmation) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    if (await signUp(email.trim(), password, name.trim())) {
      // Creating an account does not sign anyone in. They arrive at sign
      // in and use the password once, which is where they will start from
      // every time after this.
      navigate("/signin", { replace: true, state: { created: true } });
    }
  };

  return (
    <div className="page">
      <h1 className="page-title">Create an account</h1>
      <p className="page-lead">
        With an account, the text you record is kept and you can read it back later.
      </p>

      <form className="account-panel" onSubmit={(event) => void submit(event)}>
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
            autoComplete="new-password"
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
              setMismatch(false);
            }}
            required
            minLength={MIN_PASSWORD}
          />
        </label>
        <label className="account-field">
          <span>Confirm password</span>
          <input
            type="password"
            autoComplete="new-password"
            value={confirmation}
            onChange={(event) => {
              setConfirmation(event.target.value);
              setMismatch(false);
            }}
            required
            aria-invalid={mismatchNow || mismatch}
            aria-describedby={mismatchNow || mismatch ? "password-mismatch" : undefined}
          />
        </label>

        {(mismatchNow || mismatch) && (
          <p className="account-notice" id="password-mismatch" role="alert">
            {MISMATCH}
          </p>
        )}
        {notice && (
          <p className="account-notice" role="alert">
            {notice}
          </p>
        )}

        <div className="account-actions">
          <Link className="account-link" to="/signin" onClick={dismissNotice}>
            I already have an account
          </Link>
          <button
            type="submit"
            className="primary-button account-submit"
            disabled={busy || mismatchNow}
          >
            {busy ? "Working" : "Create account"}
          </button>
        </div>
      </form>
    </div>
  );
}
