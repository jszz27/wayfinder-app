import { useEffect, useState } from "react";

import { useAccount } from "../auth/AuthProvider";
import { buildTranscript, downloadTranscript } from "../captions/transcript";
import { CaptionPanel } from "../components/CaptionPanel";
import { GuidePanel } from "../components/GuidePanel";
import { ModeTabs, type Mode } from "../components/ModeTabs";
import { ScreenPill } from "../components/ScreenPill";
import { SettingsBar, FONT_SIZES } from "../components/SettingsBar";
import { SourcePill } from "../components/SourcePill";
import { useGuideSession } from "../guide/useGuideSession";
import { saveTranscript } from "../sessions/api";
import { useCaptionSession, type SessionStatus } from "../useCaptionSession";
import type { AudioSource } from "../ws/protocol";

// Plan.md section 8: the status line changes with the chosen source,
// because the two behave differently -- a microphone is granted once and
// then simply listens, while playing audio has to be chosen every session.
const STATUS_TEXT: Record<AudioSource, Record<SessionStatus, string>> = {
  mic: {
    idle: "Press Start to begin listening through your microphone.",
    starting: "Preparing the microphone…",
    listening: "Listening through the microphone…",
    reconnecting: "Connection lost. Reconnecting…",
    stopping: "Finishing up…",
  },
  tab_audio: {
    idle: "Press Start, then choose the tab or screen you are listening to.",
    starting: "Waiting for you to choose what to share…",
    listening: "Listening to the shared audio…",
    reconnecting: "Connection lost. Reconnecting…",
    stopping: "Finishing up…",
  },
};

function guideStatusText(sending: boolean, complete: boolean, sharing: boolean): string {
  if (complete) return "This conversation is finished.";
  if (sending) return "Working out the next step…";
  if (sharing) return "The guide can see your screen when you send a question.";
  return "Ask what to do next, one step at a time.";
}

/** Renders a BCP-47 tag as a language name, e.g. ko-KR -> Korean.
 *
 * Only the primary subtag is named, because the full tag reads as a
 * dialect -- "American English", "Korean (South Korea)" -- which is more
 * than the chip is claiming. Mandarin is reported as cmn, which
 * Intl.DisplayNames does not know by that name.
 */
function languageName(tag: string): string {
  const primary = tag.split("-")[0] ?? tag;
  const forDisplay = primary === "cmn" || primary === "yue" ? "zh" : primary;
  try {
    return new Intl.DisplayNames(["en"], { type: "language" }).of(forDisplay) ?? tag;
  } catch {
    return tag;
  }
}

export function HomePage() {
  const [mode, setMode] = useState<Mode>("caption");
  const [source, setSource] = useState<AudioSource>("mic");
  const [fontSize, setFontSize] = useState<number>(FONT_SIZES[1]);
  const [keeping, setKeeping] = useState(false);
  const [kept, setKept] = useState(false);
  const [keepError, setKeepError] = useState<string | null>(null);

  const auth = useAccount();
  const signedIn = auth.status === "signed-in";
  const autoSave = auth.account?.auto_save ?? false;
  // Only a signed-in listener with auto-save on gets a session row, and
  // only a session row gets a transcript written to it.
  const persist = signedIn && autoSave;

  const { status, lines, notice, language, reset, start, stop, dismissNotice } =
    useCaptionSession(source, persist);
  const guide = useGuideSession();

  // A saved text size follows the account to whatever device it is signed
  // in on, which for someone who needs larger text is most of the reason
  // to have an account at all.
  useEffect(() => {
    if (auth.account) setFontSize(auth.account.font_size);
  }, [auth.account]);

  const changeFontSize = (size: number) => {
    setFontSize(size);
    void auth.rememberFontSize(size);
  };

  const forget = () => {
    setKept(false);
    setKeepError(null);
  };

  const keep = async () => {
    setKeeping(true);
    setKeepError(null);
    try {
      await saveTranscript(source, buildTranscript(lines));
      setKept(true);
    } catch (error) {
      setKeepError(error instanceof Error ? error.message : "Could not save this text.");
    } finally {
      setKeeping(false);
    }
  };

  const running = status !== "idle";
  const stopped = !running && lines.length > 0;
  const guideSending = guide.status === "sending";
  const guideComplete = guide.status === "complete";

  return mode === "caption" ? (
    <>
      <ModeTabs mode={mode} onChange={setMode} />

      {/* The audio source is fixed for the whole session (Plan.md
          section 5), so the control locks while a stream is open. */}
      <SourcePill source={source} onChange={setSource} locked={running} />
      <div className="status-row">
        <p className="status-text" aria-live="polite">
          {STATUS_TEXT[source][status]}
        </p>
        {language && (
          <span className="language-chip" aria-live="polite">
            {languageName(language)}
          </span>
        )}
      </div>

      <CaptionPanel
        lines={lines}
        fontSize={fontSize}
        placeholder="Captions will appear here."
      />

      {notice && (
        <div className="notice" role="alert">
          <span>{notice}</span>
          <button type="button" className="notice-dismiss" onClick={dismissNotice}>
            Dismiss
          </button>
        </div>
      )}
      {keepError && (
        <div className="notice" role="alert">
          <span>{keepError}</span>
          <button
            type="button"
            className="notice-dismiss"
            onClick={() => setKeepError(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {running ? (
        <button
          type="button"
          className="primary-button is-running"
          onClick={() => void stop()}
          disabled={status === "starting" || status === "stopping"}
        >
          Stop
        </button>
      ) : stopped ? (
        /* Stopping with a transcript on screen is a fork, not an end.
           Reset only clears -- it does not start listening, because
           discarding a transcript and deciding to record again are two
           decisions, not one.

           What sits beside it depends on where the words are going. With
           auto-save on they are already in the account, so the offer is to
           carry on adding to that same entry. With auto-save off nothing
           has been written anywhere yet, so the offer is to write it. */
        <div className="button-row">
          <button
            type="button"
            className="secondary-button"
            onClick={() => {
              forget();
              reset();
            }}
          >
            Reset
          </button>
          {signedIn && !autoSave ? (
            <button
              type="button"
              className="primary-button"
              onClick={() => void keep()}
              disabled={keeping || kept}
            >
              {kept ? "Saved to your account" : keeping ? "Saving…" : "Save to my account"}
            </button>
          ) : (
            <button
              type="button"
              className="primary-button"
              onClick={() => void start(true)}
            >
              Continue
            </button>
          )}
        </div>
      ) : (
        <button
          type="button"
          className="primary-button"
          onClick={() => {
            forget();
            void start(false);
          }}
        >
          Start
        </button>
      )}

      {/* Keeping what was said is the other half of being able to follow
          it, so this stays available while listening, and to anyone -- it
          is the only copy a signed-out listener will ever have. */}
      <button
        type="button"
        className="secondary-button"
        onClick={() => downloadTranscript(lines)}
        disabled={lines.length === 0}
      >
        Save as text file
      </button>

      <SettingsBar fontSize={fontSize} onFontSizeChange={changeFontSize} />

      {signedIn ? (
        <div className="settings-bar">
          <span className="settings-label" id="auto-save-label">
            Auto-save
          </span>
          <div
            className="settings-options"
            role="radiogroup"
            aria-labelledby="auto-save-label"
          >
            {[true, false].map((on) => (
              <button
                key={String(on)}
                type="button"
                role="radio"
                className="settings-option"
                aria-checked={autoSave === on}
                /* Changing this mid-session would move where the words
                   already on screen were going, so it waits. */
                disabled={running}
                onClick={() => void auth.rememberAutoSave(on)}
              >
                {on ? "On" : "Off"}
              </button>
            ))}
          </div>
          <span className="account-status">
            {autoSave
              ? "Stopping keeps this text in your account."
              : "Nothing is kept until you save it."}
          </span>
        </div>
      ) : (
        <p className="account-status">
          Not signed in, so nothing is being saved to an account.
        </p>
      )}
    </>
  ) : (
    <>
      <ModeTabs mode={mode} onChange={setMode} />

      {/* Plan.md section 10: screen sharing is never implicit -- the user
          turns it on, and can see and turn it off at any time. */}
      <ScreenPill
        sharing={guide.sharing}
        busy={guideSending}
        onTurnOn={() => void guide.startSharing()}
        onTurnOff={guide.stopSharing}
      />
      <div className="status-row">
        <p className="status-text" aria-live="polite">
          {guideStatusText(guideSending, guideComplete, guide.sharing)}
        </p>
      </div>

      <GuidePanel
        messages={guide.messages}
        fontSize={fontSize}
        sending={guideSending}
        complete={guideComplete}
        onSend={(text) => void guide.send(text)}
      />

      {guide.notice && (
        <div className="notice" role="alert">
          <span>{guide.notice}</span>
          <button type="button" className="notice-dismiss" onClick={guide.dismissNotice}>
            Dismiss
          </button>
        </div>
      )}

      {guideComplete ? (
        <button type="button" className="primary-button" onClick={guide.reset}>
          Start a new conversation
        </button>
      ) : (
        guide.hasSession && (
          <button
            type="button"
            className="secondary-button"
            onClick={() => void guide.finish()}
            disabled={guideSending}
          >
            Finish this conversation
          </button>
        )
      )}

      <SettingsBar fontSize={fontSize} onFontSizeChange={changeFontSize} />
    </>
  );
}
