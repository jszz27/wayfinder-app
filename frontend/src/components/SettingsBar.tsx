import { CAPTION_LANGUAGES } from "../captions/languages";

interface SettingsBarProps {
  fontSize: number;
  onFontSizeChange: (size: number) => void;
  /** Null means detect the language rather than pin it. */
  language: string | null;
  onLanguageChange: (language: string | null) => void;
  /** A stream is pinned for its whole life, so this locks while one is open. */
  languageLocked: boolean;
}

export const FONT_SIZES = [16, 20, 26, 34] as const;
const LABELS = ["Small", "Medium", "Large", "Extra large"];

const DETECT = "detect";

// Plan.md section 8: only accessibility-critical settings are exposed.
// Text size stays a row of pills -- four options, and the choice is worth
// seeing all at once. Language is a menu instead: twelve pills would out-
// weigh everything above them, and this is a setting most people touch
// once, if ever.
export function SettingsBar({
  fontSize,
  onFontSizeChange,
  language,
  onLanguageChange,
  languageLocked,
}: SettingsBarProps) {
  return (
    <div className="settings">
      <div className="settings-bar">
        <span className="settings-label" id="font-size-label">
          Text size
        </span>
        <div className="settings-options" role="radiogroup" aria-labelledby="font-size-label">
          {FONT_SIZES.map((size, index) => (
            <button
              key={size}
              type="button"
              role="radio"
              className="settings-option"
              aria-checked={fontSize === size}
              onClick={() => onFontSizeChange(size)}
            >
              {LABELS[index]}
            </button>
          ))}
        </div>
      </div>

      <div className="settings-bar">
        <label className="settings-label" htmlFor="caption-language">
          Language
        </label>
        <select
          id="caption-language"
          className="settings-select"
          value={language ?? DETECT}
          disabled={languageLocked}
          onChange={(event) =>
            onLanguageChange(event.target.value === DETECT ? null : event.target.value)
          }
        >
          {/* First and default. Detection handles a speaker who changes
              language mid-session, which a pinned stream cannot. */}
          <option value={DETECT}>Detect automatically</option>
          {CAPTION_LANGUAGES.map(({ tag, name }) => (
            <option key={tag} value={tag}>
              {name}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
