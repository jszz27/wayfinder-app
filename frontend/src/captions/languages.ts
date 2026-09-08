// The languages the widget offers to pin, and what to call them.
//
// These are the eleven Wayfinder claims to support -- the same set
// `backend-ws/app/stt/detect.py` can name from audio. The tags are the
// full ones the streaming model wants, not the bare subtags detection
// reports: Mandarin in particular is only ever "cmn-Hans-CN" there.
//
// The socket accepts any well-formed tag, so this list is what is offered
// rather than what is allowed. Pinning a language the recogniser supports
// but detection does not stays possible; it is simply not a menu item.

export interface CaptionLanguage {
  tag: string;
  name: string;
}

export const CAPTION_LANGUAGES: CaptionLanguage[] = [
  { tag: "en-US", name: "English" },
  { tag: "ko-KR", name: "Korean" },
  { tag: "es-ES", name: "Spanish" },
  { tag: "cmn-Hans-CN", name: "Chinese (Mandarin)" },
  { tag: "ja-JP", name: "Japanese" },
  { tag: "fr-FR", name: "French" },
  { tag: "hi-IN", name: "Hindi" },
  { tag: "ar-EG", name: "Arabic" },
  { tag: "pt-BR", name: "Portuguese" },
  { tag: "de-DE", name: "German" },
  { tag: "ru-RU", name: "Russian" },
];

/** What to call a pinned tag, including one that is not on the menu. */
export function pinnedLanguageName(tag: string): string {
  return CAPTION_LANGUAGES.find((language) => language.tag === tag)?.name ?? tag;
}
