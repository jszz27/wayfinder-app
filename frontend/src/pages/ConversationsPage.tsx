import { useCallback, useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { useAccount } from "../auth/AuthProvider";
import {
  deleteConversation,
  listConversations,
  renameConversation,
  type SavedConversation,
} from "../guide/api";
import { SavedNav } from "../components/SavedNav";
import { whenItHappened } from "./SavedListPage";

export function ConversationsPage() {
  const { status } = useAccount();
  const [conversations, setConversations] = useState<SavedConversation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setConversations(await listConversations());
    setError(null);
  }, []);

  useEffect(() => {
    if (status !== "signed-in") return;
    void load().catch((problem: unknown) =>
      setError(problem instanceof Error ? problem.message : "Could not load these."),
    );
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

  return (
    <div className="page">
      <Link className="account-link" to="/">
        &larr; Back to the main page
      </Link>

      <h1 className="page-title">Guide conversations</h1>
      <SavedNav here="conversations" />

      {error && (
        <div className="notice" role="alert">
          <span>{error}</span>
          <button type="button" className="notice-dismiss" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {conversations === null ? (
        !error && <p className="account-status">Loading&hellip;</p>
      ) : conversations.length === 0 ? (
        <p className="page-lead">
          {/* With auto-save off nothing arrives here on its own, so this
              does not promise that it will. */}
          Nothing here yet. Conversations you keep on the{" "}
          <Link className="account-link" to="/">
            main page
          </Link>{" "}
          appear here.
        </p>
      ) : (
        <ul className="saved-list">
          {conversations.map((conversation) => (
            <li key={conversation.id} className="saved-item">
              {renaming === conversation.id ? (
                <form
                  className="saved-rename"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void act(conversation.id, () =>
                      renameConversation(conversation.id, draft),
                    ).then(() => setRenaming(null));
                  }}
                >
                  <label className="visually-hidden" htmlFor={`name-${conversation.id}`}>
                    Name for this conversation
                  </label>
                  <input
                    id={`name-${conversation.id}`}
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
                <Link className="saved-name" to={`/conversations/${conversation.id}`}>
                  {/* Until it is named, the first question is what makes
                      one recognisable a week later. */}
                  {conversation.title ??
                    conversation.opening ??
                    "A conversation with no questions"}
                </Link>
              )}

              <p className="saved-meta">
                {whenItHappened(conversation.started_at)} ·{" "}
                {conversation.exchanges === 1
                  ? "1 question"
                  : `${conversation.exchanges} questions`}
                {conversation.completed_at && " · finished"}
              </p>

              <div className="saved-actions">
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy === conversation.id}
                  onClick={() => {
                    setDraft(conversation.title ?? "");
                    setRenaming(conversation.id);
                  }}
                >
                  Rename
                </button>
                {confirming === conversation.id ? (
                  <>
                    {/* Deleting cannot be undone, so it takes a second,
                        deliberate press -- as on the saved text list. */}
                    <button
                      type="button"
                      className="secondary-button is-danger"
                      disabled={busy === conversation.id}
                      onClick={() =>
                        void act(conversation.id, () =>
                          deleteConversation(conversation.id),
                        ).then(() => setConfirming(null))
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
                    disabled={busy === conversation.id}
                    onClick={() => setConfirming(conversation.id)}
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
