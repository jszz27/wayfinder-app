// Split out so components can take these types without importing the hook,
// which would drag the whole auth client into a file that only renders.

export type { Account } from "./api";
export type { AuthStatus } from "./useAuth";
