import { Popover } from "radix-ui";
import type { Clip } from "@/api/types";
import { SCORE_TEXT, scoreTone } from "@/lib/clips";
import { cn } from "@/lib/utils";
import { ScoreBreakdown } from "./ScoreBreakdown";

/**
 * The virality score of a clip as a big colored number (green from 80,
 * yellow from 60, gray below). Clicking it opens the breakdown: Hook, Flow,
 * Value and Trend bars and the reason the clip was picked.
 */
export function ScoreBadge({ clip }: { clip: Clip }) {
  const { overall } = clip.scores;
  const tone = scoreTone(overall);

  return (
    <Popover.Root>
      <Popover.Trigger
        aria-label={`Score ${overall}, show breakdown`}
        data-tone={tone}
        className={cn(
          "rounded-md px-1 text-3xl leading-none font-bold tabular-nums outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
          SCORE_TEXT[tone],
        )}
      >
        {overall}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={8}
          className="z-50 w-72 rounded-xl border border-border bg-popover p-4 text-popover-foreground shadow-popover outline-none"
        >
          <ScoreBreakdown clip={clip} />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
