import { useState, type ReactNode } from "react";
import type { AttemptSource, Phrase } from "./api";
import PracticeCard from "./PracticeCard";

export interface DrillItem {
  phrase: Phrase;
  /** Letters whose scores are highlighted in the result. */
  focus?: string[];
}

interface Props {
  items: DrillItem[];
  source: AttemptSource;
  hideHints?: boolean;
  timing?: boolean;
  banner?: ReactNode;
  onResult?: () => void;
  onFinish?: () => void;
  finishLabel?: string;
}

/** Steps through items one at a time with a PracticeCard. The last item's Next finishes (or restarts) the drill. */
export default function Drill({ items, source, hideHints, timing, banner, onResult, onFinish, finishLabel }: Props) {
  const [index, setIndex] = useState(0);
  const item = items[index];
  if (!item) return null;
  const isLast = index === items.length - 1;
  const restart = items.length > 1 ? () => setIndex(0) : undefined;
  return (
    <>
      {banner}
      <PracticeCard
        key={`${index}-${item.phrase.text}`}
        phrase={item.phrase}
        source={source}
        focus={item.focus}
        hideHints={hideHints}
        timing={timing}
        position={items.length > 1 ? `${index + 1} / ${items.length}` : undefined}
        onPrev={index > 0 ? () => setIndex(index - 1) : undefined}
        onNext={isLast ? (onFinish ?? restart) : () => setIndex(index + 1)}
        nextLabel={isLast ? (onFinish ? finishLabel : "↻ Start again") : undefined}
        onResult={onResult}
      />
    </>
  );
}
