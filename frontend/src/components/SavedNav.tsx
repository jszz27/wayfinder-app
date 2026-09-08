import { Link } from "react-router-dom";

/** Moves between the two kinds of thing an account keeps.
 *
 * One header button leads here rather than two, because "what have I
 * saved" is one question -- the answer just has two halves.
 */
export function SavedNav({ here }: { here: "text" | "conversations" }) {
  return (
    <nav className="saved-nav" aria-label="Saved">
      {here === "text" ? (
        <span className="saved-nav-here" aria-current="page">
          Text
        </span>
      ) : (
        <Link className="saved-nav-link" to="/saved">
          Text
        </Link>
      )}
      {here === "conversations" ? (
        <span className="saved-nav-here" aria-current="page">
          Guide conversations
        </span>
      ) : (
        <Link className="saved-nav-link" to="/conversations">
          Guide conversations
        </Link>
      )}
    </nav>
  );
}
