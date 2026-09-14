import type { LetterResult, WordResult } from "./api";

const ACUTE = "́";
const VOWELS = "аеёиоуыэюя";

export function Letters({ letters }: { letters: LetterResult[] }) {
  // Stress marks only help in words with more than one vowel.
  const showStress = letters.filter((l) => VOWELS.includes(l.char.toLowerCase())).length > 1;
  return (
    <>
      {letters.map((l, i) => (
        <span
          key={i}
          className={`letter ${l.status}`}
          title={
            l.status === "silent"
              ? "silent / not pronounced separately"
              : l.heard_as
                ? `sounded like “${l.heard_as}”`
                : undefined
          }
        >
          {l.char}
          {l.stressed && showStress && l.char.toLowerCase() !== "ё" ? ACUTE : ""}
        </span>
      ))}
    </>
  );
}

interface DetailProps {
  word: WordResult;
  onListen: (text: string, speed: "normal" | "slow") => void;
}

/** Breakdown of one word: letter colours, what each problem letter sounded like, and word audio. */
export function WordDetail({ word, onListen }: DetailProps) {
  const problems = word.letters.filter((l) => l.status === "wrong" || l.status === "close");
  const silent = word.letters.filter((l) => l.status === "silent");
  return (
    <div className="word-detail">
      <div className="word-detail-head">
        <span className="word-big" lang="ru">
          <Letters letters={word.letters} />
        </span>
        <span className={`pill ${word.status}`}>{word.score}%</span>
        <button onClick={() => onListen(word.text, "normal")}>🔊</button>
        <button onClick={() => onListen(word.text, "slow")}>🐢</button>
      </div>
      {word.status === "missing" ? (
        <p>I didn't hear this word. Listen to it, then try saying it on its own.</p>
      ) : problems.length === 0 ? (
        <p>All sounds in this word were clear.</p>
      ) : (
        <ul>
          {problems.map((l, i) => (
            <li key={i}>
              <strong lang="ru" className={`letter ${l.status}`}>{l.char.toLowerCase()}</strong>{" "}
              {l.heard_as ? (
                <>
                  sounded like <strong lang="ru">{l.heard_as}</strong>
                </>
              ) : (
                "wasn't clear"
              )}
              {l.status === "close" ? " (almost)" : ""}
            </li>
          ))}
        </ul>
      )}
      {silent.length > 0 && (
        <p className="muted">
          Faded letters (<span lang="ru">{silent.map((l) => l.char).join(", ")}</span>) aren't pronounced separately.
        </p>
      )}
      {word.heard && word.recognized !== "correct" && (
        <p className="muted">
          Speech recognition heard: <span lang="ru">{word.heard}</span>
        </p>
      )}
    </div>
  );
}
