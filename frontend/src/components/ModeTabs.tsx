export type Mode = "caption" | "guide";

interface ModeTabsProps {
  mode: Mode;
  onChange: (mode: Mode) => void;
}

// Plan.md section 8: the whole feature set sits behind two tabs. There is
// no routing -- everything lives in this one widget.
export function ModeTabs({ mode, onChange }: ModeTabsProps) {
  return (
    <div className="mode-tabs" role="tablist" aria-label="Mode">
      <button
        type="button"
        role="tab"
        className="mode-tab"
        aria-selected={mode === "caption"}
        onClick={() => onChange("caption")}
      >
        Live captions
      </button>
      <button
        type="button"
        role="tab"
        className="mode-tab"
        aria-selected={mode === "guide"}
        disabled
        title="Guide mode arrives in a later sprint."
      >
        Digital guide
      </button>
    </div>
  );
}
