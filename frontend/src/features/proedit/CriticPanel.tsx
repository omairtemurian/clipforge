import type { CriticRound, PlanChange, ProEditRun } from "@/api/types";
import { KIND_LABELS } from "./laneMath";
import { splitNotes } from "./editNotes";

const SCORE_MAX = 10;
const OP_LABEL = { add: "Added", remove: "Removed", modify: "Modified" };

function changeLabel(change: PlanChange): string {
  const item = change.after ?? change.before;
  const kind = item ? KIND_LABELS[item.kind] : "item";
  return `${OP_LABEL[change.op]} ${kind} #${change.item_id}`;
}

/** One critic round: its scores and what it changed. */
function Round({ round }: { round: CriticRound }) {
  return (
    <section
      aria-label={`Critic round ${round.round}`}
      className="flex flex-col gap-2"
    >
      <h4 className="text-body font-medium">
        Round {round.round}
        {round.plan_version !== null && (
          <span className="text-muted-foreground">
            {" "}
            · scored plan v{round.plan_version}
          </span>
        )}
      </h4>
      <ul aria-label="Scores" className="flex flex-col gap-1.5">
        {round.scores.map((score) => (
          <li key={score.check} className="text-body">
            <div className="flex items-center justify-between gap-3">
              <span>{score.check}</span>
              <span className="tabular-nums">
                {score.score}/{SCORE_MAX}
              </span>
            </div>
            <div
              aria-hidden
              className="h-1.5 overflow-hidden rounded-full bg-muted"
            >
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${(score.score / SCORE_MAX) * 100}%` }}
              />
            </div>
            {score.reason && (
              <span className="text-caption text-muted-foreground">
                {score.reason}
              </span>
            )}
          </li>
        ))}
      </ul>
      {round.changes.length > 0 && (
        <ul aria-label="What changed" className="text-body">
          {round.changes.map((change) => (
            <li key={`${change.op}-${change.item_id}`}>
              <span className="font-medium">{changeLabel(change)}</span>
              <span className="block text-muted-foreground">
                {change.reason}
              </span>
            </li>
          ))}
        </ul>
      )}
      {round.ignored.length > 0 && (
        <ul
          aria-label="Not applied"
          className="text-body text-muted-foreground"
        >
          {round.ignored.map((ignored, index) => (
            <li key={index}>
              Not applied: {ignored.problem} ({ignored.reason})
            </li>
          ))}
        </ul>
      )}
      {round.notes.map((note) => (
        <p key={note} className="text-body text-muted-foreground">
          {note}
        </p>
      ))}
    </section>
  );
}

/**
 * The critic's verdict of the latest run (SPEC-v3 3.7/3.8): per round the
 * 0-10 score and reason of every checklist point, and what the critic
 * changed in the plan ("what changed"), what it asked for that was not
 * applied, and the notes of the run (but the edit notes: RunNotes).
 */
export function CriticPanel({ run }: { run: ProEditRun | undefined }) {
  return (
    <section aria-label="Critic" className="flex flex-col gap-3">
      <h3 className="text-body font-semibold">Critic</h3>
      {run ? (
        <>
          {run.critic_scores.map((round) => (
            <Round key={round.round} round={round} />
          ))}
          {splitNotes(run.notes).others.map((note) => (
            <p key={note} className="text-body text-muted-foreground">
              {note}
            </p>
          ))}
        </>
      ) : (
        <p className="text-body text-muted-foreground">
          The critic has not scored this variant yet.
        </p>
      )}
    </section>
  );
}
