import { useMemo, useState } from "react";
import ActionBar from "./ActionBar";
import { api, type AlphabetLetter } from "./api";
import { useAudio } from "./useAudio";
import { useHotkeys } from "./useHotkeys";

const QUESTIONS = 10;

interface Question {
  letter: AlphabetLetter;
  options: string[];
  showUpper: boolean;
}

function shuffle<T>(items: T[]): T[] {
  const a = [...items];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function buildQuiz(letters: AlphabetLetter[], allLetters: AlphabetLetter[]): Question[] {
  const pool: AlphabetLetter[] = [];
  while (pool.length < QUESTIONS) pool.push(...shuffle(letters));
  return pool.slice(0, QUESTIONS).map((letter, i) => {
    // Distractors: the English lookalike first (e.g. В → "b"), then other letters' sounds.
    const others = shuffle(allLetters.filter((l) => l.latin !== letter.latin).map((l) => l.latin));
    const distractors = [...new Set([...(letter.confusable ?? []), ...others])].slice(0, 3);
    return { letter, options: shuffle([letter.latin, ...distractors]), showUpper: i % 2 === 0 };
  });
}

interface Props {
  letters: AlphabetLetter[];
  allLetters: AlphabetLetter[];
  onDone: () => void;
  doneLabel: string;
}

export default function LetterQuiz({ letters, allLetters, onDone, doneLabel }: Props) {
  const [round, setRound] = useState(0);
  const questions = useMemo(() => buildQuiz(letters, allLetters), [letters, allLetters, round]);
  const [index, setIndex] = useState(0);
  const [chosen, setChosen] = useState<string | null>(null);
  const [correct, setCorrect] = useState(0);
  const audio = useAudio();

  const q = questions[index];
  const finished = index >= questions.length;

  const choose = (option: string) => {
    if (chosen || !q) return;
    setChosen(option);
    if (option === q.letter.latin) setCorrect((c) => c + 1);
    audio.play(api.ttsUrl(q.letter.examples[0].text, "normal"));
  };

  const next = () => {
    setChosen(null);
    setIndex((i) => i + 1);
  };

  const retry = () => {
    setRound((r) => r + 1);
    setIndex(0);
    setCorrect(0);
  };

  const hearAgain = () => q && audio.play(api.ttsUrl(q.letter.examples[0].text, "slow"));

  useHotkeys((key) => {
    const n = Number(key);
    if (finished) {
      if (key === "enter") onDone();
      else if (key === "r") retry();
      else return false;
    } else if (!chosen && n >= 1 && n <= q.options.length) choose(q.options[n - 1]);
    else if (chosen && (key === "enter" || key === "space" || key === "arrowright")) next();
    else if (chosen && (key === "l" || key === "s")) hearAgain();
    else return false;
    return true;
  });

  if (finished) {
    const pct = Math.round((correct / questions.length) * 100);
    return (
      <div className="card quiz">
        <h2>
          {correct} / {questions.length} correct
        </h2>
        <p>{pct >= 80 ? "Great, you know these letters! 🎉" : "Have another go: these take a few rounds to stick."}</p>
        <ActionBar
          center={<button onClick={retry}>↻ Try again</button>}
          right={
            <button className="primary" onClick={onDone}>
              {doneLabel}
            </button>
          }
          hint={
            <>
              <kbd>Enter</kbd> continue · <kbd>R</kbd> try again
            </>
          }
        />
      </div>
    );
  }

  const example = q.letter.examples[0];
  return (
    <div className="card quiz">
      <div className="card-top">
        <span className="category">
          Question {index + 1} / {questions.length}
        </span>
        <span className="best">Score: {correct}</span>
      </div>
      <p className="quiz-prompt">What sound does this letter make?</p>
      <div className="big-letter quiz-letter" lang="ru">
        {q.showUpper ? q.letter.upper : q.letter.lower}
      </div>
      <div className="quiz-options">
        {q.options.map((opt, i) => {
          const state = !chosen ? "" : opt === q.letter.latin ? "right" : opt === chosen ? "wrong" : "dim";
          return (
            <button key={opt} className={`quiz-option ${state}`} onClick={() => choose(opt)} disabled={!!chosen}>
              <kbd>{i + 1}</kbd> {opt}
            </button>
          );
        })}
      </div>
      {chosen && (
        <div className={`quiz-feedback ${chosen === q.letter.latin ? "right" : "wrong"}`}>
          <strong>{chosen === q.letter.latin ? "Correct!" : `Not quite: it's “${q.letter.latin}”.`}</strong>{" "}
          <span lang="ru">
            {q.letter.upper}
            {q.letter.lower}
          </span>{" "}
          sounds like {q.letter.sound}. Example: <span lang="ru">{example.plain}</span> ({example.english}).
          {q.letter.false_friend && chosen !== q.letter.latin && <div className="muted">{q.letter.false_friend}</div>}
        </div>
      )}
      <ActionBar
        center={
          <button onClick={hearAgain} disabled={!chosen} title="Hear the example slowly (L)">
            🐢 Hear example
          </button>
        }
        right={
          <button className={chosen ? "primary" : ""} onClick={next} disabled={!chosen} title="Next (Enter)">
            {index === questions.length - 1 ? "See score →" : "Next →"}
          </button>
        }
        hint={
          chosen ? (
            <>
              <kbd>Enter</kbd> next · <kbd>L</kbd> hear example
            </>
          ) : (
            <>
              <kbd>1</kbd>–<kbd>{q.options.length}</kbd> choose an answer
            </>
          )
        }
      />
    </div>
  );
}
