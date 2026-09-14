import { api, type AlphabetLetter, type LetterMastery } from "./api";
import Stressed from "./Stressed";
import { useAudio } from "./useAudio";

interface Props {
  letter: AlphabetLetter;
  mastery?: LetterMastery;
  onPractise: () => void;
}

const KIND_LABEL = { vowel: "Vowel", consonant: "Consonant", sign: "Sign (no sound)" };

export default function LetterCard({ letter, mastery, onPractise }: Props) {
  const audio = useAudio();
  const play = (text: string, speed: "normal" | "slow" = "normal") => audio.play(api.ttsUrl(text, speed));

  return (
    <div className="card letter-card">
      <div className="card-top">
        <span className="category">{KIND_LABEL[letter.kind]}</span>
        {mastery && (
          <span className={`best ${mastery.status}`}>
            {mastery.status === "mastered" ? "Mastered" : "Learning"} · {Math.round(mastery.average * 100)}%
          </span>
        )}
      </div>

      <div className="letter-hero">
        <div className="big-letter" lang="ru">
          {letter.upper}
          <span>{letter.lower}</span>
        </div>
        <div className="letter-facts">
          <div className="letter-sound">
            Sounds like <strong>{letter.sound}</strong>
          </div>
          <div className="letter-name">
            Name: <Stressed text={letter.name_display} />
            <button className="icon" onClick={() => play(letter.name)} title="Hear the letter's name">
              🔊
            </button>
          </div>
        </div>
      </div>

      {letter.false_friend && <div className="warning">⚠️ {letter.false_friend}</div>}
      {letter.tip && <div className="note">💡 {letter.tip}</div>}

      <h3>Hear it</h3>
      <div className="chips">
        {letter.syllables.map((s) => (
          <button key={s.text} className="chip" onClick={() => play(s.text, "slow")} title={s.translit}>
            🔊 <Stressed text={s.display} />
          </button>
        ))}
      </div>

      <h3>In words</h3>
      <ul className="examples">
        {letter.examples.map((ex) => (
          <li key={ex.text}>
            <button className="icon" onClick={() => play(ex.text)} title="Listen">
              🔊
            </button>
            <button className="icon" onClick={() => play(ex.text, "slow")} title="Listen slowly">
              🐢
            </button>
            <span className="example-word">
              <HighlightLetter text={ex.display} letter={letter.lower} />
            </span>
            <span className="muted">{ex.translit}</span>
            <span className="example-english">{ex.english}</span>
          </li>
        ))}
      </ul>

      <div className="controls">
        <button className="record" onClick={onPractise}>
          🎙 Practise saying <span lang="ru">{letter.upper}</span>
        </button>
      </div>
    </div>
  );
}

/** Stress-aware word display with every occurrence of `letter` emphasised. */
function HighlightLetter({ text, letter }: { text: string; letter: string }) {
  const parts: { s: string; hit: boolean }[] = [];
  for (let i = 0; i < text.length; i++) {
    let ch = text[i];
    if (text[i + 1] === "́") ch += text[++i];
    const hit = ch[0].toLowerCase() === letter;
    const last = parts[parts.length - 1];
    if (last && last.hit === hit && !hit) last.s += ch;
    else parts.push({ s: ch, hit });
  }
  return (
    <span lang="ru" className="ru">
      {parts.map((p, i) =>
        p.hit ? (
          <mark key={i}>{p.s}</mark>
        ) : (
          <Stressed key={i} text={p.s} />
        ),
      )}
    </span>
  );
}
