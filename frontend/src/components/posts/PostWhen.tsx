import {
  CalendarBlankIcon,
  CalendarDotsIcon,
  CircleNotchIcon,
  PaperPlaneTiltIcon,
} from "@phosphor-icons/react";
import type { ScheduleRules } from "@/api/types";
import { Field, INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import type { BulkFields, WhenMode } from "@/lib/postForm";
import { cn } from "@/lib/utils";

type Day = ScheduleRules["skip_days"][number];

const DAYS: { day: Day; label: string }[] = [
  { day: "mon", label: "Mon" },
  { day: "tue", label: "Tue" },
  { day: "wed", label: "Wed" },
  { day: "thu", label: "Thu" },
  { day: "fri", label: "Fri" },
  { day: "sat", label: "Sat" },
  { day: "sun", label: "Sun" },
];

const SUBMIT_LABEL: Record<WhenMode, string> = {
  now: "Post now",
  at: "Schedule",
  bulk: "Schedule in free slots",
};

const CHIP =
  "rounded-full border border-border px-2.5 py-0.5 text-xs transition-colors hover:bg-muted aria-pressed:border-destructive/60 aria-pressed:text-muted-foreground aria-pressed:line-through";

interface PostWhenProps {
  mode: WhenMode;
  onModeChange: (mode: WhenMode) => void;
  at: string;
  onAtChange: (local: string) => void;
  bulk: BulkFields;
  onBulkChange: (fields: BulkFields) => void;
  /** What keeps the posts from going out, if anything. */
  problem: string | null;
  busy: boolean;
  onSubmit: () => void;
}

/** The bulk scheduler's simple rules: times of day, posts per day, the
 * days to skip and the first day (the browser's timezone). */
export function BulkRules({
  bulk,
  onChange,
}: Pick<PostWhenProps, "bulk"> & { onChange: (fields: BulkFields) => void }) {
  const toggle = (day: Day) =>
    onChange({
      ...bulk,
      skipDays: bulk.skipDays.includes(day)
        ? bulk.skipDays.filter((each) => each !== day)
        : [...bulk.skipDays, day],
    });
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <Field label="Times of day" htmlFor="bulk-times">
        <input
          id="bulk-times"
          value={bulk.times}
          placeholder="09:00, 18:00"
          onChange={(event) => onChange({ ...bulk, times: event.target.value })}
          className={cn(INPUT, "h-9")}
        />
      </Field>
      <Field label="Posts per day" htmlFor="bulk-per-day">
        <input
          id="bulk-per-day"
          type="number"
          min={1}
          max={24}
          value={bulk.postsPerDay}
          onChange={(event) =>
            onChange({
              ...bulk,
              postsPerDay: Math.max(1, Number(event.target.value)),
            })
          }
          className={cn(INPUT, "h-9")}
        />
      </Field>
      <Field label="First day" htmlFor="bulk-start">
        <input
          id="bulk-start"
          type="date"
          value={bulk.startDate}
          onChange={(event) =>
            onChange({ ...bulk, startDate: event.target.value })
          }
          className={cn(INPUT, "h-9")}
        />
      </Field>
      <div
        role="group"
        aria-label="Skip days"
        className="flex flex-wrap gap-1.5 sm:col-span-3"
      >
        <span className="mr-1 text-sm text-muted-foreground">Skip</span>
        {DAYS.map(({ day, label }) => (
          <button
            key={day}
            type="button"
            aria-pressed={bulk.skipDays.includes(day)}
            onClick={() => toggle(day)}
            className={CHIP}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

/** The modal's footer: "Bulk schedule" (each account's next free slots),
 * "Pick time" and the primary button that posts now or schedules. */
export function PostWhen({
  mode,
  onModeChange,
  at,
  onAtChange,
  bulk,
  onBulkChange,
  problem,
  busy,
  onSubmit,
}: PostWhenProps) {
  const pick = (next: WhenMode) => onModeChange(mode === next ? "now" : next);
  return (
    <div className="flex flex-col gap-4 border-t border-border pt-4">
      {mode === "at" && (
        <Field label="Publish at" htmlFor="post-at">
          <input
            id="post-at"
            type="datetime-local"
            value={at}
            onChange={(event) => onAtChange(event.target.value)}
            className={cn(INPUT, "h-9 sm:w-64")}
          />
        </Field>
      )}
      {mode === "bulk" && <BulkRules bulk={bulk} onChange={onBulkChange} />}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          aria-pressed={mode === "bulk"}
          onClick={() => pick("bulk")}
        >
          <CalendarBlankIcon aria-hidden />
          Bulk schedule
        </Button>
        <Button
          type="button"
          variant="outline"
          aria-pressed={mode === "at"}
          onClick={() => pick("at")}
        >
          <CalendarDotsIcon aria-hidden />
          Pick time
        </Button>
        {problem && (
          <p role="status" className="ml-auto text-sm text-muted-foreground">
            {problem}
          </p>
        )}
        <Button
          type="button"
          className={cn(!problem && "ml-auto")}
          disabled={problem !== null || busy}
          onClick={onSubmit}
        >
          {busy ? (
            <CircleNotchIcon className="animate-spin" aria-hidden />
          ) : (
            <PaperPlaneTiltIcon aria-hidden />
          )}
          {SUBMIT_LABEL[mode]}
        </Button>
      </div>
    </div>
  );
}
