import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { useAccount } from "../auth/AuthProvider";
import { listConversations, type SavedConversation } from "../guide/api";
import { SavedNav } from "../components/SavedNav";
import { whenItHappened } from "./SavedListPage";

export function ConversationsPage() {
  const { status } = useAccount();
  const [conversations, setConversations] = useState<SavedConversation[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status !== "signed-in") return;
    let current = true;
    void (async () => {
      try {
        const rows = await listConversations();
        if (current) setConversations(rows);
      } catch (problem) {
        if (current) {
          setError(
            problem instanceof Error ? problem.message : "Could not load these.",
          );
        }
      }
    })();
    return () => {
      current = false;
    };
  }, [status]);

  if (status === "loading") {
    return <p className="account-status">Checking your account&hellip;</p>;
  }
  if (status === "signed-out") return <Navigate to="/signin" replace />;

  return (
    <div className="page">
      <Link className="account-link" to="/">
        &larr; Live captions
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
          Nothing here yet. Ask the guide something on the{" "}
          <Link className="account-link" to="/">
            main page
          </Link>{" "}
          and the conversation will be kept.
        </p>
      ) : (
        <ul className="saved-list">
          {conversations.map((conversation) => (
            <li key={conversation.id} className="saved-item">
              <Link className="saved-name" to={`/conversations/${conversation.id}`}>
                {/* A conversation has no name, so the first question is
                    what makes it recognisable a week later. */}
                {conversation.opening ?? "A conversation with no questions"}
              </Link>
              <p className="saved-meta">
                {whenItHappened(conversation.started_at)} ·{" "}
                {conversation.exchanges === 1
                  ? "1 question"
                  : `${conversation.exchanges} questions`}
                {conversation.completed_at && " · finished"}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
