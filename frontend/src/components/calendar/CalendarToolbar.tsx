import { CaretLeftIcon, CaretRightIcon } from "@phosphor-icons/react";
import type { SocialAccount } from "@/api/types";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import {
  STATUS_LABELS,
  rangeTitle,
  type CalendarFilters,
  type CalendarView,
  type PostStatus,
} from "@/lib/calendar";
import { PLATFORM_LABELS, type SocialPlatform } from "@/lib/platforms";

const VIEWS: { view: CalendarView; label: string }[] = [
  { view: "month", label: "Month" },
  { view: "week", label: "Week" },
];

const SEGMENT =
  "rounded-full px-3 py-1 text-sm text-muted-foreground transition-colors outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 aria-pressed:bg-card aria-pressed:text-foreground aria-pressed:shadow-card";

interface CalendarToolbarProps {
  view: CalendarView;
  onViewChange: (view: CalendarView) => void;
  anchor: Date;
  onStep: (step: number) => void;
  onToday: () => void;
  filters: CalendarFilters;
  onFiltersChange: (filters: CalendarFilters) => void;
  accounts: SocialAccount[];
}

/** The calendar's bar: Month/Week and Today (left), the month or week
 * title between previous/next arrows (centre), the platform, account and
 * status filters (right); the filters wrap below when narrow. */
export function CalendarToolbar({
  view,
  onViewChange,
  anchor,
  onStep,
  onToday,
  filters,
  onFiltersChange,
  accounts,
}: CalendarToolbarProps) {
  const unit = view === "month" ? "month" : "week";
  const platforms = Object.keys(PLATFORM_LABELS) as SocialPlatform[];
  const set = (change: Partial<CalendarFilters>) =>
    onFiltersChange({ ...filters, ...change });

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="flex items-center gap-2">
        <div
          role="group"
          aria-label="Calendar view"
          className="inline-flex rounded-full bg-muted p-0.5"
        >
          {VIEWS.map((each) => (
            <button
              key={each.view}
              type="button"
              aria-pressed={view === each.view}
              onClick={() => onViewChange(each.view)}
              className={SEGMENT}
            >
              {each.label}
            </button>
          ))}
        </div>
        <Button variant="outline" onClick={onToday}>
          Today
        </Button>
      </div>
      <div className="mx-auto flex items-center justify-center gap-4">
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Previous ${unit}`}
          onClick={() => onStep(-1)}
        >
          <CaretLeftIcon aria-hidden />
        </Button>
        <h2 className="min-w-48 text-center text-section" aria-live="polite">
          {rangeTitle(anchor, view)}
        </h2>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Next ${unit}`}
          onClick={() => onStep(1)}
        >
          <CaretRightIcon aria-hidden />
        </Button>
      </div>
      <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
        <NativeSelect
          aria-label="Platform"
          value={filters.platform}
          onChange={(event) =>
            set({ platform: event.target.value as CalendarFilters["platform"] })
          }
        >
          <option value="all">All platforms</option>
          {platforms.map((platform) => (
            <option key={platform} value={platform}>
              {PLATFORM_LABELS[platform]}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="Account"
          className="max-w-48"
          value={String(filters.accountId)}
          onChange={(event) =>
            set({
              accountId:
                event.target.value === "all"
                  ? "all"
                  : Number(event.target.value),
            })
          }
        >
          <option value="all">All accounts</option>
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.display_name} ({PLATFORM_LABELS[account.platform]})
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="Status"
          value={filters.status}
          onChange={(event) =>
            set({ status: event.target.value as CalendarFilters["status"] })
          }
        >
          <option value="all">All statuses</option>
          {(Object.keys(STATUS_LABELS) as PostStatus[]).map((status) => (
            <option key={status} value={status}>
              {STATUS_LABELS[status]}
            </option>
          ))}
        </NativeSelect>
      </div>
    </div>
  );
}
