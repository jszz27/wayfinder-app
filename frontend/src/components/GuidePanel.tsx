import { useEffect, useRef, useState } from "react";

import type { GuideMessage } from "../guide/api";

interface GuidePanelProps {
  messages: GuideMessage[];
  fontSize: number;
  sending: boolean;
  complete: boolean;
  onSend: (text: string) => void;
}

const PLACEHOLDER = "Describe what you are stuck on.";

// Plan.md section 8: a chat-style UI. The answer is what the reader needs,
// so it carries the weight; their own question stays quieter above it.
export function GuidePanel({
  messages,
  fontSize,
  sending,
  complete,
  onSend,
}: GuidePanelProps) {
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [messages, sending]);

  const submit = () => {
    const text = draft.trim();
    if (!text || sending || complete) return;
    onSend(text);
    setDraft("");
  };

  return (
    <div className="guide">
      <div
        className="guide-transcript"
        style={{ fontSize: `${fontSize}px` }}
        ref={scrollRef}
        role="log"
        aria-live="polite"
        aria-label="Guide conversation"
      >
        {messages.length === 0 && !sending ? (
          <p className="caption-placeholder">
            Ask what to do next. Turn on the screen reference above and the guide
            can look at your screen as it answers.
          </p>
        ) : (
          <>
            {messages.map((message) => (
              <p
                key={message.id}
                className={
                  message.role === "user" ? "guide-line is-asked" : "guide-line is-answer"
                }
              >
                {message.content}
              </p>
            ))}
            {sending && (
              <p className="guide-line is-thinking" aria-live="polite">
                Looking&hellip;
              </p>
            )}
          </>
        )}
      </div>

      <div className="guide-composer">
        <label className="visually-hidden" htmlFor="guide-input">
          Your question
        </label>
        <textarea
          id="guide-input"
          className="guide-input"
          rows={2}
          value={draft}
          placeholder={complete ? "This conversation is finished." : PLACEHOLDER}
          disabled={complete}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            // Enter sends; Shift+Enter starts a new line.
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <button
          type="button"
          className="primary-button guide-send"
          onClick={submit}
          disabled={sending || complete || draft.trim().length === 0}
        >
          {sending ? "Sending" : "Send"}
        </button>
      </div>
    </div>
  );
}
