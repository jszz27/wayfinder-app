import { useCallback, useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { useAccount } from "../auth/AuthProvider";
import { downloadText, savedFilename } from "../captions/transcript";
import { SavedNav } from "../components/SavedNav";
import {
  deleteSession,
  getSession,
  listSessions,
  renameSession,
  type SavedSession,
} from "../sessions/api";

/** "8 September 2026, 14:32" -- the name a session has until it is given one. */
export function whenItHappened(startedAt: string): string {
  const at = new Date(startedAt);
  if (Number.isNaN(at.getTime())) return "Unknown date";
  // English, like the rest of the interface and like the language chip
  // on the captions page; the transcript may be in any language but the
  // app around it is not.
  return at.toLocaleString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function SavedListPage() {
  const { status } = useAccount();
  const [sessions, setSessions] = useState<SavedSession[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setSessions(await listSessions());
      setError(null);
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "Could not load your saved text.");
    }
  }, []);

  useEffect(() => {
    if (status === "signed-in") void load();
  }, [load, status]);

  if (status === "loading") {
    return <p className="account-status">Checking your account&hellip;</p>;
  }
  if (status === "signed-out") return <Navigate to="/signin" replace />;

  const act = async (id: string, work: () => Promise<unknown>) => {
    setBusy(id);
    setError(null);
    try {
      await work();
      await load();
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "That did not work.");
    } finally {
      setBusy(null);
    }
  };

  const download = (session: SavedSession) =>
    act(session.id, async () => {
      const full = await getSession(session.id);
      downloadText(full.text, savedFilename(full.title, full.started_at));
    });

  return (
    <div className="page">
      {/* The way back is the first thing on every page here, in the same
          place and pointing one level up -- the session detail page has
          the same link back to this list. It names where it goes rather
          than what is there: "live captions" is one of two things on that
          page, and reads as a feature you are switching to rather than
          the way out of this one. */}
      <Link className="account-link" to="/">
        &larr; Back to the main page
      </Link>

      <h1 className="page-title">Saved text</h1>
      <SavedNav here="text" />

      {error && (
        <div className="notice" role="alert">
          <span>{error}</span>
          <button type="button" className="notice-dismiss" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {sessions === null ? (
        <p className="account-status">Loading&hellip;</p>
      ) : sessions.length === 0 ? (
        <p className="page-lead">
          Nothing saved yet. Record something on the{" "}
          <Link className="account-link" to="/">
            captions page
          </Link>{" "}
          and it will appear here.
        </p>
      ) : (
        <ul className="saved-list">
          {sessions.map((session) => (
            <li key={session.id} className="saved-item">
              {renaming === session.id ? (
                <form
                  className="saved-rename"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void act(session.id, () => renameSession(session.id, draft)).then(() =>
                      setRenaming(null),
                    );
                  }}
                >
                  <label className="visually-hidden" htmlFor={`name-${session.id}`}>
                    Name for this text
                  </label>
                  <input
                    id={`name-${session.id}`}
                    type="text"
                    value={draft}
                    maxLength={120}
                    autoFocus
                    onChange={(event) => setDraft(event.target.value)}
                  />
                  <button type="submit" className="secondary-button">
                    Save name
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => setRenaming(null)}
                  >
                    Cancel
                  </button>
                </form>
              ) : (
                <Link className="saved-name" to={`/saved/${session.id}`}>
                  {session.title ?? whenItHappened(session.started_at)}
                </Link>
              )}

              <p className="saved-meta">
                {/* An unnamed session is already shown by its date above,
                    so repeating it here would say nothing. */}
                {session.title !== null && whenItHappened(session.started_at)}
                {session.title !== null && session.edited && " · "}
                {session.edited && "edited"}
                {session.title === null && !session.edited && "Not yet named"}
              </p>

              <div className="saved-actions">
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy === session.id}
                  onClick={() => {
                    setDraft(session.title ?? "");
                    setRenaming(session.id);
                  }}
                >
                  Rename
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy === session.id}
                  onClick={() => void download(session)}
                >
                  Download
                </button>
                {confirming === session.id ? (
                  <>
                    {/* Deleting is the one thing here that cannot be
                        undone, so it takes a second, deliberate press. */}
                    <button
                      type="button"
                      className="secondary-button is-danger"
                      disabled={busy === session.id}
                      onClick={() =>
                        void act(session.id, () => deleteSession(session.id)).then(() =>
                          setConfirming(null),
                        )
                      }
                    >
                      Delete for good
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => setConfirming(null)}
                    >
                      Keep it
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="secondary-button is-danger"
                    disabled={busy === session.id}
                    onClick={() => setConfirming(session.id)}
                  >
                    Delete
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
