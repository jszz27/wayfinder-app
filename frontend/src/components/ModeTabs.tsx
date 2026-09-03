export type Mode = "caption" | "guide";

interface ModeTabsProps {
  mode: Mode;
  onChange: (mode: Mode) => void;
}

// Plan.md section 8: the whole feature set sits behind two tabs. There is
// no routing -- everything lives in this one widget.
export function ModeTabs({ mode, onChange }: ModeTabsProps) {
  return (
    <div className="mode-tabs" role="tablist" aria-label="모드 선택">
      <button
        type="button"
        role="tab"
        className="mode-tab"
        aria-selected={mode === "caption"}
        onClick={() => onChange("caption")}
      >
        실시간 자막
      </button>
      <button
        type="button"
        role="tab"
        className="mode-tab"
        aria-selected={mode === "guide"}
        disabled
        title="가이드 모드는 다음 스프린트에서 추가됩니다."
      >
        디지털 가이드
      </button>
    </div>
  );
}
