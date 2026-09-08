import { createContext, useContext, type ReactNode } from "react";

import { useAuth } from "./useAuth";

type Auth = ReturnType<typeof useAuth>;

// One signed-in session, shared by every page. Before routing this lived
// inside the widget; now that the saved list and a session's own page are
// real pages, each of them needs the same account, and refreshing the
// token once per page would sign the other two out.
const AuthContext = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  return <AuthContext.Provider value={useAuth()}>{children}</AuthContext.Provider>;
}

export function useAccount(): Auth {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAccount must be used inside an AuthProvider");
  return auth;
}
