// Mirror of packages/nihaixia_core/chat_text.py: strips markdown formatting from
// chat answers so the plain-text chat UI and TTS never surface raw symbols.

const HEADING_RE = /^\s{0,3}#{1,6}\s*/;
const NUMBERED_RE = /^\s*(\d{1,2})\s*[.、)）]\s+/;
const BULLET_RE = /^\s*[-*•·]\s+/;
const BOLD_RE = /\*\*(.+?)\*\*/g;
const UNDERLINE_BOLD_RE = /__(.+?)__/g;
const ITALIC_RE = /(^|[^*])\*([^*\n]+)\*(?!\*)/g;
const INLINE_CODE_RE = /`([^`\n]*)`/g;
const CODE_FENCE_RE = /^\s*```.*$/;
const TABLE_ROW_RE = /^\s*\|.*\|\s*$/;
const TABLE_RULE_RE = /^\s*\|?[\s:|-]+\|?\s*$/;

const ORDINALS = ["一是", "二是", "三是", "四是", "五是", "六是", "七是", "八是", "九是", "十是"];

function replaceNumberedMarker(line: string) {
  const match = NUMBERED_RE.exec(line);
  if (!match) return line;
  const index = Number(match[1]);
  const rest = line.slice(match[0].length);
  if (index >= 1 && index <= ORDINALS.length) {
    return `${ORDINALS[index - 1]}${rest}`;
  }
  return rest;
}

function flattenTableRow(line: string) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim())
    .filter(Boolean)
    .join("，");
}

export function sanitizeChatText(text: string) {
  if (!text) return "";

  const cleaned = text.split(/\r?\n/).flatMap((rawLine) => {
    if (CODE_FENCE_RE.test(rawLine)) return [];
    if (TABLE_ROW_RE.test(rawLine) && TABLE_RULE_RE.test(rawLine)) return [];
    let line = rawLine.replace(HEADING_RE, "").replace(BULLET_RE, "");
    line = replaceNumberedMarker(line);
    if (TABLE_ROW_RE.test(line)) {
      line = flattenTableRow(line);
    }
    return [line];
  });

  return cleaned
    .join("\n")
    .replace(BOLD_RE, "$1")
    .replace(UNDERLINE_BOLD_RE, "$1")
    .replace(ITALIC_RE, "$1$2")
    .replace(INLINE_CODE_RE, "$1")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
