import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useBlocker, useParams } from "react-router-dom";

import { useAccount } from "../auth/AuthProvider";
import { downloadText, savedFilename } from "../captions/transcript";
import { FONT_SIZES } from "../components/SettingsBar";
import { getSession, saveSessionText, type SavedSessionDetail } from "../sessions/api";
import { whenItHappened } from "./SavedListPage";

const UNSAVED = "You have unsaved changes.";
const UNSAVED_BEFORE_DOWNLOAD =
  "You have unsaved changes. Would you like to save before downloading?";

export function SessionDetailPage() {
  const { id = "" } = useParams();
  const { status, account } = useAccount();
  const [session, setSession] = useState<SavedSessionDetail | null>(null);
  const [text, setText] = useState("");
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState<"download" | "discard" | null>(null);

  const dirty = editing && session !== null && text !== session.text;

  useEffect(() => {
    let current = true;
    void (async () => {
      try {
        const found = await getSession(id);
        if (!current) return;
        setSession(found);
        setText(found.text);
      } catch (problem) {
        if (current) {
          setError(problem instanceof Error ? problem.message : "Could not open that text.");
        }
      }
    })();
    return () => {
      current = false;
    };
  }, [id]);

  // Closing the tab or reloading. The browser shows its own wording here
  // and refuses to show ours, so this is the warning existing rather than
  // the warning reading the way the rest of the page does.
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  // Navigating away inside the app, where the wording is ours.
  const blocker = useBlocker(dirty);

  if (status === "loading") {
    return <p className="account-status">Checking your account&hellip;</p>;
  }
  if (status === "signed-out") return <Navigate to="/signin" replace />;

  const save = async () => {
    if (!session) return false;
    setSaving(true);
    setError(null);
    try {
      await saveSessionText(session.id, text);
      setSession({ ...session, text, edited: true });
      setEditing(false);
      return true;
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "Could not save your changes.");
      return false;
    } finally {
      setSaving(false);
    }
  };

  const download = (what: string) => {
    if (!session) return;
    downloadText(what, savedFilename(session.title, session.started_at));
  };

  const askedToDownload = () => {
    if (dirty) setAsking("download");
    else download(text);
  };

  const askedToStopEditing = () => {
    if (dirty) setAsking("discard");
    else setEditing(false);
  };

  const discard = () => {
    if (session) setText(session.text);
    setEditing(false);
    setAsking(null);
  };

  const readingSize = `${account?.font_size ?? FONT_SIZES[1]}px`;

  return (
    <div className="page">
      <Link className="account-link" to="/saved">
        &larr; All saved text
      </Link>

      {error && (
        <div className="notice" role="alert">
          <span>{error}</span>
          <button type="button" className="notice-dismiss" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {session === null ? (
        !error && <p className="account-status">Loading&hellip;</p>
      ) : (
        <>
          <h1 className="page-title">
            {session.title ?? whenItHappened(session.started_at)}
          </h1>
          <p className="saved-meta">
            {whenItHappened(session.started_at)}
            {session.edited && " · edited"}
            {dirty && " · unsaved changes"}
          </p>

          {editing ? (
            <label className="session-editor">
              <span className="visually-hidden">The text of this session</span>
              <textarea
                value={text}
                onChange={(event) => setText(event.target.value)}
                style={{ fontSize: readingSize }}
                autoFocus
              />
            </label>
          ) : (
            <p className="session-text" style={{ fontSize: readingSize }}>
              {session.text || "This session has no text."}
            </p>
          )}

          <div className="button-row">
            {editing ? (
              <>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={askedToStopEditing}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="primary-button"
                  onClick={() => void save()}
                  disabled={saving || !dirty}
                >
                  {saving ? "Saving…" : "Save"}
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={askedToDownload}
                >
                  Download as Text File
                </button>
                <button
                  type="button"
                  className="primary-button"
                  onClick={() => setEditing(true)}
                >
                  Edit
                </button>
              </>
            )}
          </div>

          {/* Downloading is offered while editing too, because wanting a
              copy of what you have just corrected is the obvious moment to
              want one -- and it is the moment the prompt is for. */}
          {editing && (
            <button type="button" className="secondary-button" onClick={askedToDownload}>
              Download as Text File
            </button>
          )}
        </>
      )}

      {blocker.state === "blocked" && (
        <Prompt
          message={UNSAVED}
          actions={[
            { label: "Stay on this page", cancel: true, onClick: () => blocker.reset() },
            {
              label: "Leave without saving",
              danger: true,
              onClick: () => blocker.proceed(),
            },
          ]}
        />
      )}

      {asking === "download" && (
        <Prompt
          message={UNSAVED_BEFORE_DOWNLOAD}
          actions={[
            { label: "Cancel", cancel: true, onClick: () => setAsking(null) },
            {
              label: "Download without saving",
              onClick: () => {
                setAsking(null);
                download(text);
              },
            },
            {
              label: "Save, then download",
              primary: true,
              onClick: () => {
                setAsking(null);
                void save().then((saved) => {
                  if (saved) download(text);
                });
              },
            },
          ]}
        />
      )}

      {asking === "discard" && (
        <Prompt
          message={UNSAVED}
          actions={[
            { label: "Keep editing", cancel: true, onClick: () => setAsking(null) },
            { label: "Discard changes", danger: true, onClick: discard },
          ]}
        />
      )}
    </div>
  );
}

interface PromptAction {
  label: string;
  onClick: () => void;
  primary?: boolean;
  danger?: boolean;
  /** The way out: what Escape does, and where focus lands on opening. */
  cancel?: boolean;
}

/** A dialog that behaves like one.
 *
 * `aria-modal` is a claim, not a mechanism. Without the four things below
 * it was a claim this dialog could not back: focus stayed on the button
 * behind it, Tab walked out into eight other controls, and Escape did
 * nothing. For someone using a keyboard or a screen reader that is not a
 * modal -- it is a picture of one, over a page they are still standing in.
 *
 * The four: focus moves in on opening, Tab cycles within, Escape takes
 * the way out, and focus returns to whatever opened it.
 */
function Prompt({ message, actions }: { message: string; actions: PromptAction[] }) {
  const dialog = useRef<HTMLDivElement>(null);
  const cancelIndex = Math.max(
    actions.findIndex((action) => action.cancel),
    0,
  );

  useEffect(() => {
    // Whatever had focus before, so it can be handed back. Losing your
    // place on the page is its own small harm.
    const opener = document.activeElement as HTMLElement | null;
    const buttons = () =>
      Array.from(dialog.current?.querySelectorAll("button") ?? []);

    // The safe option, not the destructive one: a dialog that opens with
    // "Leave without saving" under the cursor is a trap.
    buttons()[cancelIndex]?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        actions[cancelIndex]?.onClick();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = buttons();
      if (focusable.length === 0) return;
      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;
      const on = document.activeElement;
      // Wrap at both ends, so Tab cannot walk out of the dialog into the
      // page it is covering.
      if (event.shiftKey && (on === first || !dialog.current?.contains(on))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && on === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      opener?.focus?.();
    };
    // Mounted once per dialog, and the actions belong to that one dialog.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="prompt-backdrop">
      <div
        className="prompt"
        role="alertdialog"
        aria-modal="true"
        aria-label={message}
        ref={dialog}
      >
        <p className="prompt-message">{message}</p>
        <div className="prompt-actions">
          {actions.map((action) => (
            <button
              key={action.label}
              type="button"
              className={
                action.primary
                  ? "primary-button"
                  : action.danger
                    ? "secondary-button is-danger"
                    : "secondary-button"
              }
              onClick={action.onClick}
            >
              {action.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
