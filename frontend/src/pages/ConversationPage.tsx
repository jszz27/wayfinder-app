import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { useAccount } from "../auth/AuthProvider";
import { FONT_SIZES } from "../components/SettingsBar";
import { getGuideSession, type GuideSession } from "../guide/api";
import { whenItHappened } from "./SavedListPage";

export function ConversationPage() {
  const { id = "" } = useParams();
  const { status, account } = useAccount();
  const [conversation, setConversation] = useState<GuideSession | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    void (async () => {
      try {
        const found = await getGuideSession(id);
        if (current) setConversation(found);
      } catch (problem) {
        if (current) {
          setError(
            problem instanceof Error ? problem.message : "Could not open that.",
          );
        }
      }
    })();
    return () => {
      current = false;
    };
  }, [id]);

  if (status === "loading") {
    return <p className="account-status">Checking your account&hellip;</p>;
  }
  if (status === "signed-out") return <Navigate to="/signin" replace />;

  const readingSize = `${account?.font_size ?? FONT_SIZES[1]}px`;
  const asked = conversation?.messages.find((message) => message.role === "user");

  return (
    <div className="page">
      <Link className="account-link" to="/conversations">
        &larr; All conversations
      </Link>

      {error && (
        <div className="notice" role="alert">
          <span>{error}</span>
          <button type="button" className="notice-dismiss" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {conversation === null ? (
        !error && <p className="account-status">Loading&hellip;</p>
      ) : (
        <>
          <h1 className="page-title">{asked?.content ?? "A conversation"}</h1>
          <p className="saved-meta">
            {whenItHappened(conversation.started_at)}
            {conversation.completed_at && " · finished"}
          </p>

          {/* The same shape the live chat uses: the question stays quiet,
              the answer carries the weight, because the answer is what
              the reader came back for. */}
          <div className="guide-transcript" style={{ fontSize: readingSize }}>
            {conversation.messages.length === 0 ? (
              <p className="caption-placeholder">Nothing was asked in this one.</p>
            ) : (
              conversation.messages.map((message) => (
                <p
                  key={message.id}
                  className={`guide-line ${
                    message.role === "user" ? "is-asked" : "is-answer"
                  }`}
                >
                  {message.content}
                </p>
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}
