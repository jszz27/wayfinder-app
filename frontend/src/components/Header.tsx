import { Link } from "react-router-dom";

import { useAccount } from "../auth/AuthProvider";

// The two tabs are still the whole feature set (Plan.md section 8, as
// amended); this header is only about whose account is in use, which is
// what the saved text belongs to.
export function Header() {
  const { status, account, signOut } = useAccount();

  return (
    <header className="app-header">
      <Link className="app-brand" to="/">
        Wayfinder
      </Link>

      {status === "loading" ? (
        <span className="account-status">Checking your account&hellip;</span>
      ) : status === "signed-in" && account ? (
        <nav className="header-actions" aria-label="Account">
          <span className="account-status">{account.display_name}</span>
          <Link className="header-button" to="/saved">
            Saved Text List
          </Link>
          <button
            type="button"
            className="header-button"
            onClick={() => void signOut()}
          >
            Sign out
          </button>
        </nav>
      ) : (
        <nav className="header-actions" aria-label="Account">
          <Link className="header-button" to="/signup">
            Create account
          </Link>
          <Link className="header-button" to="/signin">
            Sign in
          </Link>
        </nav>
      )}
    </header>
  );
}
