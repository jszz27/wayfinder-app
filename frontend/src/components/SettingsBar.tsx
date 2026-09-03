interface SettingsBarProps {
  fontSize: number;
  onFontSizeChange: (size: number) => void;
}

export const FONT_SIZES = [16, 20, 26, 34] as const;
const LABELS = ["Small", "Medium", "Large", "Extra large"];

// Plan.md section 8: only accessibility-critical settings are exposed.
// Language joins this row in Sprint 3; see docs/sprint-1.md.
export function SettingsBar({ fontSize, onFontSizeChange }: SettingsBarProps) {
  return (
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
  );
}
