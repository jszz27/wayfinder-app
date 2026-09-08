import { useEffect, useState } from "react";

import { useAccount } from "../auth/AuthProvider";
import { pinnedLanguageName } from "../captions/languages";
import { buildTranscript, downloadTranscript } from "../captions/transcript";
import { CaptionPanel } from "../components/CaptionPanel";
import { GuidePanel } from "../components/GuidePanel";
import { ModeTabs, type Mode } from "../components/ModeTabs";
import { ScreenPill } from "../components/ScreenPill";
import { SettingsBar, FONT_SIZES } from "../components/SettingsBar";
import { SourcePill } from "../components/SourcePill";
import { useGuideSession } from "../guide/useGuideSession";
import { saveSessionText, saveTranscript } from "../sessions/api";
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
  // Null is detect, which is what every session did before the setting
  // existed and is still the default.
  const [language, setLanguage] = useState<string | null>(null);
  const [keeping, setKeeping] = useState(false);
  // The entry this transcript was saved as, and the text that went into
  // it. Saving again after carrying on updates that entry rather than
  // making a second one holding a copy of the first.
  const [keptAs, setKeptAs] = useState<string | null>(null);
  const [keptText, setKeptText] = useState<string | null>(null);
  const [keepError, setKeepError] = useState<string | null>(null);

  const auth = useAccount();
  const signedIn = auth.status === "signed-in";
  const autoSave = auth.account?.auto_save ?? false;
  // Only a signed-in listener with auto-save on gets a session row, and
  // only a session row gets a transcript written to it.
  const persist = signedIn && autoSave;

  const {
    status,
    lines,
    notice,
    language: detected,
    reset,
    start,
    stop,
    dismissNotice,
  } = useCaptionSession(source, persist, language);
  const guide = useGuideSession();

  // A saved text size follows the account to whatever device it is signed
  // in on, which for someone who needs larger text is most of the reason
  // to have an account at all.
  useEffect(() => {
    if (!auth.account) return;
    setFontSize(auth.account.font_size);
    setLanguage(auth.account.caption_language);
  }, [auth.account]);

  const changeFontSize = (size: number) => {
    setFontSize(size);
    void auth.rememberFontSize(size);
  };

  const changeLanguage = (tag: string | null) => {
    setLanguage(tag);
    void auth.rememberCaptionLanguage(tag);
  };

  const forget = () => {
    setKeptAs(null);
    setKeptText(null);
    setKeepError(null);
  };

  const keep = async () => {
    const text = buildTranscript(lines);
    setKeeping(true);
    setKeepError(null);
    try {
      if (keptAs === null) {
        setKeptAs((await saveTranscript(source, text)).id);
      } else {
        await saveSessionText(keptAs, text);
      }
      setKeptText(text);
    } catch (error) {
      setKeepError(error instanceof Error ? error.message : "Could not save this text.");
    } finally {
      setKeeping(false);
    }
  };

  const running = status !== "idle";
  const stopped = !running && lines.length > 0;
  // Saving by hand is offered whenever there is something to save and
  // nothing is saving it automatically.
  const canKeep = signedIn && !autoSave && lines.length > 0;
  const keptAlready = keptAs !== null && keptText === buildTranscript(lines);
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
        {/* Plan.md section 5: a pinned session reports no language,
            because nothing was worked out. The chip still says which one
            is in use -- it just is not news. */}
        {language ? (
          <span className="language-chip is-pinned">{pinnedLanguageName(language)}</span>
        ) : (
          detected && (
            <span className="language-chip" aria-live="polite">
              {languageName(detected)}
            </span>
          )
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
        /* Stopping with a transcript on screen is a fork, not an end:
           carry on after it, or clear it and be back at the beginning.
           Both sit where Stop was, so the choice is where the eye already
           is. Reset only clears -- it does not start listening, because
           discarding a transcript and deciding to record again are two
           decisions, not one.

           Carrying on is offered whether or not anything is being saved.
           Where the words go afterwards is a separate question, answered
           by the auto-save setting and by the button below. */
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
          <button
            type="button"
            className="primary-button"
            onClick={() => void start(true)}
          >
            Continue
          </button>
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

      {/* With auto-save off nothing is written until this is pressed.
          It sits with the other way of keeping a transcript rather than in
          the button row, so that stopping always offers the same two
          choices and this stays a separate decision. */}
      {canKeep && (
        <button
          type="button"
          className="secondary-button"
          onClick={() => void keep()}
          disabled={keeping || keptAlready}
        >
          {keptAlready
            ? "Saved to your account"
            : keeping
              ? "Saving…"
              : keptAs !== null
                ? "Save the rest to my account"
                : "Save to my account"}
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

      <SettingsBar
        fontSize={fontSize}
        onFontSizeChange={changeFontSize}
        language={language}
        onLanguageChange={changeLanguage}
        languageLocked={running}
      />

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

      <SettingsBar
        fontSize={fontSize}
        onFontSizeChange={changeFontSize}
        language={language}
        onLanguageChange={changeLanguage}
        languageLocked={false}
      />
    </>
  );
}
