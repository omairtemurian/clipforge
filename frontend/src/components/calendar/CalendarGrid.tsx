import { useState, type DragEvent } from "react";
import type { Post, SocialAccount } from "@/api/types";
import {
  DAY_CARD_LIMIT,
  dayKey,
  monthWeeks,
  postTime,
  postsByDay,
  weekDays,
  type CalendarView,
} from "@/lib/calendar";
import { CalendarDay } from "./CalendarDay";

interface CalendarGridProps {
  view: CalendarView;
  /** A day of the month or week shown. */
  anchor: Date;
  posts: Post[];
  accounts: Map<number, SocialAccount>;
  today: Date;
  onOpen: (post: Post) => void;
  /** A scheduled post was dropped on another day. */
  onMove: (post: Post, day: Date) => void;
}

/**
 * The calendar's grid: weekday headers (Sunday first) and a row per week
 * of the month (or one week). A month day shows at most 3 cards; "See N
 * more" expands the whole week row. A scheduled card dropped on another
 * day is moved there at the same time of day.
 */
export function CalendarGrid({
  view,
  anchor,
  posts,
  accounts,
  today,
  onOpen,
  onMove,
}: CalendarGridProps) {
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [dragged, setDragged] = useState<Post | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const weeks = view === "month" ? monthWeeks(anchor) : [weekDays(anchor)];
  const byDay = postsByDay(posts);
  const todayKey = dayKey(today);
  const from = dragged && postTime(dragged);
  const fromKey = from ? dayKey(from) : null;

  function toggle(week: string) {
    const next = new Set(expanded);
    if (!next.delete(week)) next.add(week);
    setExpanded(next);
  }

  function endDrag() {
    setDragged(null);
    setOver(null);
  }

  // Drag data cannot be read in dragover (HTML spec), so the post is kept
  // in state from dragstart.
  function dragOver(event: DragEvent, key: string) {
    if (!dragged || key === fromKey) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    setOver(key);
  }

  function drop(event: DragEvent, day: Date) {
    event.preventDefault();
    if (dragged && dayKey(day) !== fromKey) onMove(dragged, day);
    endDrag();
  }

  return (
    <div role="grid" aria-label="Posting calendar" className="min-w-[56rem]">
      <div role="row" className="grid grid-cols-7 border-b border-border">
        {weeks[0].map((day) => (
          <div
            key={day.getDay()}
            role="columnheader"
            className="py-3 text-center text-body font-medium"
          >
            {day.toLocaleDateString(undefined, { weekday: "long" })}
          </div>
        ))}
      </div>
      {weeks.map((week) => {
        const weekKey = dayKey(week[0]);
        return (
          <div
            key={weekKey}
            role="row"
            className="grid grid-cols-7 border-l border-border"
          >
            {week.map((day) => {
              const key = dayKey(day);
              return (
                <CalendarDay
                  key={key}
                  day={day}
                  posts={byDay.get(key) ?? []}
                  accounts={accounts}
                  limit={view === "month" ? DAY_CARD_LIMIT : null}
                  expanded={expanded.has(weekKey)}
                  onToggle={() => toggle(weekKey)}
                  isToday={key === todayKey}
                  outside={
                    view === "month" && day.getMonth() !== anchor.getMonth()
                  }
                  dropTarget={over === key}
                  onDragOver={(event) => dragOver(event, key)}
                  onDragLeave={() =>
                    setOver((old) => (old === key ? null : old))
                  }
                  onDrop={(event) => drop(event, day)}
                  onOpen={onOpen}
                  onDragStart={setDragged}
                  onDragEnd={endDrag}
                />
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
