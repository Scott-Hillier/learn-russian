import { useCallback, useEffect, useMemo, useState, type ComponentProps } from "react";
import {
  api,
  type Alphabet,
  type AlphabetLetter,
  type LetterMastery,
  type Lesson,
  type Phrase,
  type WordItem,
} from "./api";
import Layout from "./Layout";
import LetterCard from "./LetterCard";
import LetterQuiz from "./LetterQuiz";
import PracticeCard from "./PracticeCard";

type LayoutProps = Omit<ComponentProps<typeof Layout>, "sidebar" | "children">;
type Tab = "learn" | "say" | "read" | "quiz";
type Mastery = Record<string, LetterMastery>;

const TABS: { id: Tab; label: string }[] = [
  { id: "learn", label: "1 · Learn" },
  { id: "say", label: "2 · Say the letters" },
  { id: "read", label: "3 · Read words" },
  { id: "quiz", label: "4 · Quiz" },
];

export function letterStatus(mastery: Mastery, letter: string): "new" | "learning" | "mastered" {
  return mastery[letter.toLowerCase()]?.status ?? "new";
}

export default function AlphabetView({ layout }: { layout: LayoutProps }) {
  const [data, setData] = useState<Alphabet | null>(null);
  const [mastery, setMastery] = useState<Mastery>({});
  const [lessonId, setLessonId] = useState<number | null>(null); // null = overview
  const [tab, setTab] = useState<Tab>("learn");
  const [letter, setLetter] = useState<string | null>(null);
  const [drillFocus, setDrillFocus] = useState<string | null>(null); // practise a single letter
  const [loadError, setLoadError] = useState<string | null>(null);

  const refreshMastery = useCallback(() => {
    api.letterProgress().then(setMastery).catch(() => {});
  }, []);

  useEffect(() => {
    api
      .alphabet()
      .then(setData)
      .catch(() => setLoadError("Can't reach the backend. Is ./start.sh running?"));
    refreshMastery();
  }, [refreshMastery]);

  const letters = useMemo(() => new Map(data?.letters.map((l) => [l.upper, l]) ?? []), [data]);
  const lesson = data?.lessons.find((l) => l.id === lessonId) ?? null;

  const openLesson = (id: number, tabId: Tab = "learn", letterUpper: string | null = null) => {
    const target = data?.lessons.find((l) => l.id === id);
    setLessonId(id);
    setTab(tabId);
    setLetter(letterUpper ?? target?.letters[0] ?? null);
    setDrillFocus(null);
  };

  const sidebar = data && (
    <>
      <ul className="lesson-list">
        <li>
          <button className={lessonId === null ? "active" : ""} onClick={() => setLessonId(null)}>
            <span>All 33 letters</span>
            <small>
              {data.letters.filter((l) => letterStatus(mastery, l.lower) === "mastered").length} / 33 mastered
            </small>
          </button>
        </li>
        {data.lessons.map((ls) => {
          const done = ls.letters.filter((c) => letterStatus(mastery, c) === "mastered").length;
          return (
            <li key={ls.id}>
              <button className={lessonId === ls.id ? "active" : ""} onClick={() => openLesson(ls.id)}>
                <span>
                  {ls.id}. {ls.title}
                </span>
                <span className="mini-letters" lang="ru">
                  {ls.letters.map((c) => (
                    <span key={c} className={letterStatus(mastery, c)}>
                      {c}
                    </span>
                  ))}
                </span>
                <small>
                  {done} / {ls.letters.length} mastered
                </small>
              </button>
            </li>
          );
        })}
      </ul>
    </>
  );

  return (
    <Layout {...layout} sidebar={sidebar}>
      {loadError && <div className="banner error">{loadError}</div>}
      {data && lessonId === null && (
        <Overview data={data} mastery={mastery} onOpen={(ls, l) => openLesson(ls, "learn", l)} />
      )}
      {data && lesson && (
        <div className="lesson">
          <header className="lesson-head">
            <h2>
              Lesson {lesson.id}: {lesson.title}
            </h2>
            <p>{lesson.intro}</p>
            <div className="tabs">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  className={tab === t.id ? "active" : ""}
                  onClick={() => {
                    setTab(t.id);
                    setDrillFocus(null);
                  }}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </header>

          {tab === "learn" && (
            <>
              <div className="tile-row">
                {lesson.letters.map((c) => (
                  <LetterTile
                    key={c}
                    letter={letters.get(c)!}
                    mastery={mastery}
                    active={letter === c}
                    onClick={() => setLetter(c)}
                  />
                ))}
              </div>
              {letter && letters.get(letter) && (
                <LetterCard
                  key={letter}
                  letter={letters.get(letter)!}
                  mastery={mastery[letter.toLowerCase()]}
                  onPractise={() => {
                    setDrillFocus(letter);
                    setTab("say");
                  }}
                />
              )}
              <div className="lesson-next">
                <button className="primary" onClick={() => setTab("say")}>
                  Ready? Practise saying these letters →
                </button>
              </div>
            </>
          )}

          {tab === "say" && (
            <Drill
              key={`say-${lesson.id}-${drillFocus}`}
              items={sayItems(lesson, letters, drillFocus)}
              source="letter"
              onResult={refreshMastery}
              banner={
                drillFocus ? (
                  <div className="drill-banner">
                    Practising <strong lang="ru">{drillFocus}</strong> only ·{" "}
                    <button className="link" onClick={() => setDrillFocus(null)}>
                      practise all letters in this lesson
                    </button>
                  </div>
                ) : null
              }
              onFinish={() => setTab("read")}
              finishLabel="Next: read words →"
            />
          )}

          {tab === "read" && (
            <Drill
              key={`read-${lesson.id}`}
              items={lesson.words.map((w) => ({ word: w, focus: lesson.letters }))}
              source="reading"
              hideHints
              onResult={refreshMastery}
              onFinish={() => setTab("quiz")}
              finishLabel="Next: quiz →"
            />
          )}

          {tab === "quiz" && (
            <LetterQuiz
              key={`quiz-${lesson.id}`}
              letters={lesson.letters.map((c) => letters.get(c)!)}
              allLetters={data.letters}
              onDone={() => {
                const next = data.lessons.find((l) => l.id === lesson.id + 1);
                if (next) openLesson(next.id);
                else setLessonId(null);
              }}
              doneLabel={data.lessons.some((l) => l.id === lesson.id + 1) ? "Next lesson →" : "Back to overview"}
            />
          )}
        </div>
      )}
    </Layout>
  );
}

interface DrillItem {
  word: WordItem;
  focus: string[];
}

function sayItems(lesson: Lesson, letters: Map<string, AlphabetLetter>, only: string | null): DrillItem[] {
  const chosen = only ? [only] : lesson.letters;
  return chosen.flatMap((c) => letters.get(c)!.examples.map((word) => ({ word, focus: [c] })));
}

interface DrillProps {
  items: DrillItem[];
  source: "letter" | "reading";
  hideHints?: boolean;
  banner?: React.ReactNode;
  onResult: () => void;
  onFinish: () => void;
  finishLabel: string;
}

/** Steps through words one at a time with a PracticeCard. */
function Drill({ items, source, hideHints, banner, onResult, onFinish, finishLabel }: DrillProps) {
  const [index, setIndex] = useState(0);
  const item = items[index];
  const isLast = index === items.length - 1;
  const phrase: Phrase = {
    ...item.word,
    id: index,
    category: source === "letter" ? `Letter ${item.focus.join(", ")}` : "Reading practice",
  };
  return (
    <>
      {banner}
      <PracticeCard
        key={`${index}-${item.word.text}`}
        phrase={phrase}
        source={source}
        focus={item.focus}
        hideHints={hideHints}
        position={`${index + 1} / ${items.length}`}
        onPrev={index > 0 ? () => setIndex(index - 1) : undefined}
        onNext={isLast ? undefined : () => setIndex(index + 1)}
        onResult={onResult}
      />
      {isLast && (
        <div className="lesson-next">
          <button className="primary" onClick={onFinish}>
            {finishLabel}
          </button>
        </div>
      )}
    </>
  );
}

interface TileProps {
  letter: AlphabetLetter;
  mastery: Mastery;
  active?: boolean;
  onClick: () => void;
}

export function LetterTile({ letter, mastery, active, onClick }: TileProps) {
  const status = letterStatus(mastery, letter.lower);
  const m = mastery[letter.lower];
  return (
    <button
      className={`tile ${status}${active ? " active" : ""}`}
      onClick={onClick}
      title={m ? `${status}: ${Math.round(m.average * 100)}% over recent attempts` : "not practised yet"}
    >
      <span className="tile-letter" lang="ru">
        {letter.upper}
        {letter.lower}
      </span>
      <span className="tile-latin">{letter.latin}</span>
    </button>
  );
}

function Overview({
  data,
  mastery,
  onOpen,
}: {
  data: Alphabet;
  mastery: Mastery;
  onOpen: (lessonId: number, letter: string) => void;
}) {
  const lessonOf = (upper: string) => data.lessons.find((l) => l.letters.includes(upper))!.id;
  const counts = { new: 0, learning: 0, mastered: 0 };
  data.letters.forEach((l) => counts[letterStatus(mastery, l.lower)]++);
  const nextLesson =
    data.lessons.find((ls) => ls.letters.some((c) => letterStatus(mastery, c) !== "mastered")) ?? data.lessons[0];
  return (
    <div className="overview">
      <h2>The Russian alphabet</h2>
      <p>
        33 letters, taught in 6 lessons. Each letter turns <span className="status-word learning">amber</span> once
        you've practised it, and <span className="status-word mastered">green</span> once you say it well
        consistently.
      </p>
      <div className="overview-stats">
        <span>
          <strong>{counts.mastered}</strong> mastered
        </span>
        <span>
          <strong>{counts.learning}</strong> learning
        </span>
        <span>
          <strong>{counts.new}</strong> new
        </span>
        <button className="primary" onClick={() => onOpen(nextLesson.id, nextLesson.letters[0])}>
          {counts.new === 33 ? "Start lesson 1 →" : `Continue: lesson ${nextLesson.id} →`}
        </button>
      </div>
      <div className="tile-grid">
        {data.letters.map((l) => (
          <LetterTile key={l.upper} letter={l} mastery={mastery} onClick={() => onOpen(lessonOf(l.upper), l.upper)} />
        ))}
      </div>
    </div>
  );
}
