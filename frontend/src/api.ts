export interface Phrase {
  id: number;
  category: string;
  text: string; // with '+' stress marks
  display: string; // with accent marks
  plain: string;
  translit: string;
  english: string;
  sounds_like?: string;
  note?: string;
}

export type LetterStatus = "good" | "close" | "wrong" | "silent" | "unscored";

export interface LetterResult {
  char: string;
  stressed: boolean;
  status: LetterStatus;
  heard_as: string | null;
  score: number | null; // 0–1 for scored letters
}

/** Russian text described by the backend: stress-marked, display form and transliteration. */
export interface Described {
  text: string;
  display: string;
  plain: string;
  translit: string;
}

export interface WordItem extends Described {
  english: string;
}

export interface AlphabetLetter {
  upper: string;
  lower: string;
  name: string;
  name_display: string;
  latin: string;
  kind: "vowel" | "consonant" | "sign";
  sound: string;
  tip?: string;
  false_friend?: string;
  confusable?: string[];
  syllables: Described[]; // listen-only
  examples: WordItem[]; // speaking drill words
}

export interface Lesson {
  id: number;
  title: string;
  intro: string;
  letters: string[]; // uppercase
  words: WordItem[];
}

export interface Alphabet {
  letters: AlphabetLetter[];
  lessons: Lesson[];
}

export interface LetterMastery {
  count: number;
  average: number;
  status: "learning" | "mastered";
}

export type AttemptSource = "phrase" | "letter" | "reading" | "custom" | "flashcard" | "sentence" | "pair" | "lesson";

export interface SentenceWord extends Described {
  gloss: string;
}

export interface Sentence extends Described {
  id: number;
  theme: string;
  english: string;
  chunks: Described[];
  words: SentenceWord[];
}

export interface PairWord extends Described {
  english: string;
}

export interface PairGroup {
  id: string;
  title: string;
  letters: string[];
  explanation: string;
  priority: number;
  pairs: { a: PairWord; b: PairWord; speak: boolean }[];
  your_average: number | null;
  recommended: boolean;
}

export interface Scenario {
  id: string;
  emoji: string;
  title: string;
  role: string;
  goals: string[];
  opening: WordItem;
  phrases: WordItem[];
}

export interface ChatStatus {
  running: boolean;
  model: string;
  installed: boolean;
}

export interface ChatReply {
  reply: string;
  translation: string;
  suggestions: { russian: string; english: string }[];
  unknown?: string[]; // level "lessons": words in the reply that the lessons haven't taught yet
}

export interface ChatCheck {
  status: "correct" | "corrected" | "skipped";
  corrected: string;
  diff: { text: string; kind: "same" | "changed" | "removed" }[];
}

export interface ChatTranscript {
  text: string;
  clarity: AttemptResult | null;
}

export interface DeckCounts {
  total: number;
  new: number;
  learning: number;
  review: number;
  due: number;
  suspended: number;
}

/** Words are learned in groups: group `number` has `left` of its `size` words still to learn. */
export interface Group {
  number: number;
  size: number;
  left: number;
  learned: number;
}

export interface Deck {
  id: number;
  name: string;
  description: string;
  builtin: boolean;
  counts: DeckCounts;
  group: Group;
}

export interface FlashCard extends Described {
  id: number;
  deck_id: number;
  english: string;
  notes: string;
  tag: string;
  suspended: boolean;
  state: "new" | "learning" | "review";
  due: number | null; // unix seconds
  is_due: boolean;
  reps: number;
  lapses: number;
  needs_stress: boolean;
  builtin: boolean;
  lesson: number | null; // the course lesson that introduces this word
}

export type RatingName = "again" | "hard" | "good" | "easy";

export interface Remaining {
  due: number;
  new: number; // new words left in the current group
  new_total: number; // new words not yet learned at all
  group: Group;
  learned_words: number; // size of the Learned words deck
}

export interface StudyNext {
  next: { card: FlashCard; kind: "new" | "review"; intervals: Record<RatingName, string>; remaining: Remaining } | null;
  remaining: Remaining;
}

export interface StudyStats extends Remaining {
  reviewed_today: number;
  average_score_today: number | null;
  streak_days: number;
}

export type CourseTrack = "script" | "frames" | "vocab" | "listening" | "sounds" | "numbers" | "dialogue" | "review";
export type LessonStatus = "passed" | "available" | "locked";

/** One item of a course exercise. Which fields are set depends on the exercise type. */
export interface CourseItem {
  key?: string; // stable identity for results (not set on partner turns)
  src?: [number, number, number]; // where the item was written: lesson, exercise, item (used to check answers)
  card?: number; // review blocks: the due flashcard this item practises
  cue?: string; // emoji / picture prompt
  english?: string;
  answer?: Described; // what the learner should say (teach, say, dialogue "you" turns)
  ask?: Described; // question played before the learner answers
  audio?: Described; // choose: what is played (before answering, or after it when there's a prompt)
  prompt?: Described; // choose: written sentence with a blank, e.g. "___ дом" (options are Russian forms)
  options?: string[]; // choose
  labels?: string[]; // listening choose: the English word for an option that is only a picture ("" if none)
  correct?: number; // choose
  speaker?: "partner" | "you"; // dialogue
  line?: Described; // dialogue partner turn
}

export interface CourseExercise {
  track: CourseTrack;
  type: "teach" | "say" | "choose" | "dialogue";
  title: string;
  instruction: string;
  items: CourseItem[];
}

export interface CourseLessonSummary {
  id: number;
  title: string;
  goal: string;
  status: LessonStatus;
  exercises: number;
  exercise: number; // first exercise not yet passed
  placed: boolean; // passed by testing out of its unit
  unit: number;
  tracks: CourseTrack[];
}

/** passed · remedial (fix-up lesson first) · available (unit done: test due) · skip (test out) · locked */
export type TestStatus = "passed" | "remedial" | "available" | "skip" | "locked";

export interface CourseTestSummary {
  unit: number;
  first: number; // first and last lesson of the unit
  last: number;
  status: TestStatus;
  attempts: number;
  taken: boolean; // a mastery test was taken: the next unit is open, pass or fail
  best: number | null;
  last_accuracy: number | null;
}

export type CourseKind = "lesson" | "test" | "remedial";

export interface CourseNext {
  kind: CourseKind;
  id: number; // lesson id, or unit for tests and fix-up lessons
}

export interface CourseOverview {
  lessons: CourseLessonSummary[];
  tests: CourseTestSummary[];
  current: number | null;
  next: CourseNext | null;
  started: boolean;
  pass_accuracy: number;
  test_pass_accuracy: number;
  unit_size: number;
}

export interface CourseLesson {
  id: number; // lesson id, or unit for tests and fix-up lessons
  kind: CourseKind;
  title: string;
  goal: string;
  status: LessonStatus | TestStatus;
  exercise: number;
  exercises: CourseExercise[];
  attempt?: number; // tests: which try this is
}

export interface AnswerCheck {
  correct: boolean;
  again?: boolean; // unclear: probably the answer, but ask for it again rather than mark it wrong
  heard: string | null; // the candidate answer that matched best (display form)
  score: number; // pronunciation of the expected answer, 0–100
  words: WordResult[];
  silent: boolean; // nothing was said
  reason?: "other" | "fit" | "score" | null; // why a miss was a miss: another answer, more or less than it, or sounds off
}

export type ResultStep = "first" | "practice" | "retest" | "delayed";

export interface ItemResult {
  key: string;
  step: ResultStep;
  correct: boolean;
  override?: boolean;
  score?: number | null;
  card?: number; // a due flashcard answered in a review block (its flashcard review)
}

export interface CourseStats {
  tracks: { track: CourseTrack; tries: number; accuracy: number; recent_accuracy: number }[];
  tests: { unit: number; kind: "mastery" | "placement"; accuracy: number; passed: number; created_at: number }[];
  work_on: {
    key: string;
    track: CourseTrack;
    miss_rate: number;
    display: string;
    english: string;
    cue: string;
    src: [number, number, number];
  }[];
  first_tries: number;
  items_seen: number;
}

export interface RoundResult {
  passed: boolean;
  accuracy: number;
  exercise: number;
  lesson_passed: boolean;
  next_lesson: number | null;
  next?: CourseNext | null;
}

export interface TestResult {
  passed: boolean;
  accuracy: number;
  kind: "mastery" | "placement";
  missed: number;
  total: number;
  remedial: boolean; // an optional fix-up lesson is offered before a retake
  next: CourseNext | null;
  next_test: number | null; // placement: the next unit's test can be tried straight away
}

async function send<T>(url: string, method: string, body?: unknown): Promise<T> {
  return fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then((r) => json<T>(r));
}

export interface WordResult {
  text: string; // with '+' stress marks
  display: string;
  score: number;
  status: "good" | "close" | "wrong" | "missing";
  letters: LetterResult[];
  heard: string | null; // what speech recognition heard in this word's place
  recognized: "correct" | "close" | "wrong" | "missing";
}

export interface Timing {
  yours: number; // seconds of speech
  native: number;
  ratio: number; // yours / native
}

export interface AttemptResult {
  heard: string;
  words: WordResult[];
  extra: string[];
  score: number;
  tips: string[];
  timing?: Timing | null;
  intonation?: { native: (number | null)[]; yours: (number | null)[]; marks: { position: number; label: string }[] } | null;
}

export interface ProgressSummary {
  totals: { attempts: number; reviews: number; active_days: number; streak_days: number; average_score: number | null };
  daily: { date: string; attempts: number; reviews: number; average_score: number | null }[];
  by_source: Record<string, number>;
  letters: Record<string, LetterMastery>;
  problem_letters: (LetterMastery & { letter: string })[];
  flashcards: { learned: number; learning: number; new: number };
}

export interface Health {
  tts: string;
  asr_loaded: boolean;
  asr_model: string;
  pronunciation_loaded: boolean;
  ready: boolean;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

export const api = {
  health: () => fetch("/api/health").then((r) => json<Health>(r)),
  phrases: () => fetch("/api/phrases").then((r) => json<Phrase[]>(r)),
  alphabet: () => fetch("/api/alphabet").then((r) => json<Alphabet>(r)),
  letterProgress: () =>
    fetch("/api/progress/letters").then((r) => json<Record<string, LetterMastery>>(r)),
  describe: (text: string) =>
    fetch(`/api/describe?text=${encodeURIComponent(text)}`).then((r) => json<Phrase>(r)),
  decks: () => fetch("/api/decks").then((r) => json<Deck[]>(r)),
  createDeck: (name: string, description = "") => send<Deck>("/api/decks", "POST", { name, description }),
  deleteDeck: (id: number) => send<{ ok: boolean }>(`/api/decks/${id}`, "DELETE"),
  cards: (deckId: number) => fetch(`/api/decks/${deckId}/cards`).then((r) => json<FlashCard[]>(r)),
  addCard: (deckId: number, card: { russian: string; english: string; notes: string }) =>
    send<FlashCard>(`/api/decks/${deckId}/cards`, "POST", card),
  updateCard: (id: number, card: { russian: string; english: string; notes: string; suspended: boolean }) =>
    send<FlashCard>(`/api/cards/${id}`, "PUT", card),
  deleteCard: (id: number) => send<{ ok: boolean }>(`/api/cards/${id}`, "DELETE"),
  copyCards: (deckId: number, cardIds: number[]) =>
    send<{ added: number; skipped_duplicates: number }>(`/api/decks/${deckId}/copy`, "POST", { card_ids: cardIds }),
  removeCards: (deckId: number, cardIds: number[]) =>
    send<{ removed: number; skipped_builtin: number }>(`/api/decks/${deckId}/remove`, "POST", { card_ids: cardIds }),
  importCsv: (deckId: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`/api/decks/${deckId}/import`, { method: "POST", body: form }).then((r) =>
      json<{ added: number; skipped_duplicates: number; errors: string[] }>(r),
    );
  },
  studyNext: (deckId: number | null, newLimit: number | null = null) => {
    const params = new URLSearchParams();
    if (deckId) params.set("deck_id", String(deckId));
    if (newLimit !== null) params.set("new_limit", String(newLimit));
    return fetch(`/api/study/next?${params}`).then((r) => json<StudyNext>(r));
  },
  /** Cards for a free review pass: one deck's cards, or every learned word when no deck is given. */
  learnedCards: (deckId: number | null = null) =>
    fetch(`/api/study/learned${deckId ? `?deck_id=${deckId}` : ""}`).then((r) =>
      json<{ cards: FlashCard[] }>(r).then((d) => d.cards),
    ),
  rate: (cardId: number, rating: 1 | 2 | 3 | 4, score: number | null, practice = false) =>
    send<{ card: FlashCard; next_due_in: string | null }>(`/api/study/${cardId}/rate`, "POST", {
      rating,
      score,
      practice,
    }),
  studyStats: () => fetch("/api/study/stats").then((r) => json<StudyStats>(r)),
  settings: () => fetch("/api/settings").then((r) => json<{ group_size: number }>(r)),
  updateSettings: (groupSize: number) =>
    send<{ group_size: number }>("/api/settings", "PUT", { group_size: groupSize }),
  ttsUrl: (text: string, speed: "normal" | "slow") =>
    `/api/tts?text=${encodeURIComponent(text)}&speed=${speed}`,
  chatStatus: () => fetch("/api/chat/status").then((r) => json<ChatStatus>(r)),
  scenarios: () => fetch("/api/chat/scenarios").then((r) => json<Scenario[]>(r)),
  chatReply: (scenarioId: string, history: { role: "partner" | "learner"; text: string }[], level: string) =>
    send<ChatReply>("/api/chat/reply", "POST", { scenario_id: scenarioId, history, level }),
  chatCheck: (text: string) => send<ChatCheck>("/api/chat/check", "POST", { text }),
  chatTranscribe: (audio: Blob) => {
    const form = new FormData();
    form.append("audio", audio, "speech");
    return fetch("/api/chat/transcribe", { method: "POST", body: form }).then((r) => json<ChatTranscript>(r));
  },
  sentences: () => fetch("/api/sentences").then((r) => json<Sentence[]>(r)),
  minimalPairs: () => fetch("/api/minimal-pairs").then((r) => json<PairGroup[]>(r)),
  bestScores: (source: AttemptSource) =>
    fetch(`/api/progress/best?source=${source}`).then((r) => json<Record<string, number>>(r)),
  progressSummary: () => fetch("/api/progress/summary").then((r) => json<ProgressSummary>(r)),
  course: () => fetch("/api/course").then((r) => json<CourseOverview>(r)),
  courseLesson: (id: number) => fetch(`/api/course/${id}`).then((r) => json<CourseLesson>(r)),
  courseCheck: (src: [number, number, number], audio: Blob, testUnit?: number) => {
    const [lessonId, exercise, item] = src;
    const form = new FormData();
    form.append("exercise", String(exercise));
    form.append("item", String(item));
    if (testUnit !== undefined) form.append("test", String(testUnit));
    form.append("audio", audio, "answer");
    return fetch(`/api/course/${lessonId}/check`, { method: "POST", body: form }).then((r) => json<AnswerCheck>(r));
  },
  courseRound: (lessonId: number, exercise: number, results: ItemResult[]) =>
    send<RoundResult>(`/api/course/${lessonId}/rounds`, "POST", { exercise, results }),
  courseRestart: (lessonId: number) => send<{ ok: boolean }>(`/api/course/${lessonId}/restart`, "POST"),
  courseStats: () => fetch("/api/course/stats").then((r) => json<CourseStats>(r)),
  courseTest: (unit: number) => fetch(`/api/course/tests/${unit}`).then((r) => json<CourseLesson>(r)),
  courseTestFinish: (unit: number, results: ItemResult[]) =>
    send<TestResult>(`/api/course/tests/${unit}/finish`, "POST", { results }),
  courseRemedial: (unit: number) => fetch(`/api/course/tests/${unit}/remedial`).then((r) => json<CourseLesson>(r)),
  courseRemedialRound: (unit: number, exercise: number, results: ItemResult[]) =>
    send<RoundResult>(`/api/course/tests/${unit}/remedial/rounds`, "POST", { exercise, results }),
  attempt: (target: string, audio: Blob, source: AttemptSource, timing = false, intonation = false) => {
    const form = new FormData();
    form.append("target", target);
    form.append("source", source);
    if (timing) form.append("timing", "true");
    if (intonation) form.append("intonation", "true");
    form.append("audio", audio, "attempt");
    return fetch("/api/attempt", { method: "POST", body: form }).then((r) => json<AttemptResult>(r));
  },
};
