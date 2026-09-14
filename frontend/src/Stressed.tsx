const ACUTE = "́";

const VOWELS = "аеёиоуыэюяАЕЁИОУЫЭЮЯ";

/** "прив+ет" → "приве́т": convert '+' stress marks to combining accents for display. */
export function stressToDisplay(text: string): string {
  let out = "";
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "+" && VOWELS.includes(text[i + 1] ?? "")) {
      out += text[i + 1] + ACUTE;
      i++;
    } else out += text[i];
  }
  return out;
}

/** Renders Russian text, highlighting any vowel followed by a combining acute accent. */
export default function Stressed({ text }: { text: string }) {
  const parts: (string | { v: string })[] = [];
  let buf = "";
  for (let i = 0; i < text.length; i++) {
    if (text[i + 1] === ACUTE) {
      if (buf) parts.push(buf);
      buf = "";
      parts.push({ v: text[i] + ACUTE });
      i++;
    } else buf += text[i];
  }
  if (buf) parts.push(buf);
  return (
    <span lang="ru" className="ru">
      {parts.map((p, i) => (typeof p === "string" ? p : <span key={i} className="stress">{p.v}</span>))}
    </span>
  );
}
