import { DownloadSimpleIcon, MagnifyingGlassIcon } from "@phosphor-icons/react";
import { useState } from "react";
import type {
  ReferenceResult,
  StyleMetric,
  StyleRecipeDetail,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { INPUT } from "@/components/ui/native-select";
import { cn } from "@/lib/utils";
import { RecipeTargets } from "./RecipeTargets";
import {
  styleRecipeExportUrl,
  useAnalyzeStyleRecipe,
  usePatchStyleRecipe,
} from "./styleApi";

const LABEL = "text-body font-medium";

/** What became of a reference: analyzed, failed (why) or waiting. */
function referenceState({ reference, error }: ReferenceResult): string {
  if (error) return `Failed: ${error}`;
  if (reference.analyzed_at) return "Analyzed (media deleted)";
  return "Not analyzed yet";
}

/** The reference links of a recipe and the button that analyzes them. */
function References({ detail }: { detail: StyleRecipeDetail }) {
  const analyze = useAnalyzeStyleRecipe(detail.recipe.id);
  if (detail.references.length === 0) {
    return (
      <p className="text-body text-muted-foreground">
        Imported or made by hand: this recipe has no reference links.
      </p>
    );
  }
  const waiting = detail.references.some((r) => !r.reference.analyzed_at);
  return (
    <section aria-label="References" className="flex flex-col gap-2">
      <ul className="flex flex-col gap-1.5">
        {detail.references.map((result) => (
          <li key={result.reference.id} className="text-body">
            <span className="block truncate">{result.reference.url}</span>
            <span className="text-caption text-muted-foreground">
              {referenceState(result)}
            </span>
          </li>
        ))}
      </ul>
      <div>
        <Button
          variant="outline"
          disabled={!waiting || analyze.isPending}
          onClick={() => analyze.mutate()}
        >
          <MagnifyingGlassIcon aria-hidden />
          {analyze.isPending ? "Analyzing…" : "Analyze references"}
        </Button>
      </div>
    </section>
  );
}

/**
 * The editor of a style recipe (SPEC-v3 4.4-4.5): its name, description
 * (written by the LLM after an analysis) and target sliders, saved
 * together; its references and their analysis; and its export as a JSON
 * file without media or links. Remounted when the stored recipe changes.
 */
export function RecipeEditor({
  detail,
  metrics,
}: {
  detail: StyleRecipeDetail;
  metrics: StyleMetric[];
}) {
  const { recipe } = detail;
  const [name, setName] = useState(recipe.name);
  const [description, setDescription] = useState(recipe.description);
  const [targets, setTargets] = useState(detail.targets);
  const patch = usePatchStyleRecipe(recipe.id);
  const changed =
    name !== recipe.name ||
    description !== recipe.description ||
    JSON.stringify(targets) !== JSON.stringify(detail.targets);
  return (
    <section
      aria-label={`Recipe ${recipe.name}`}
      className="flex flex-col gap-6"
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="recipe-name" className={LABEL}>
            Name
          </label>
          <input
            id="recipe-name"
            value={name}
            maxLength={200}
            onChange={(event) => setName(event.target.value)}
            className={cn(INPUT, "h-9")}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="recipe-description" className={LABEL}>
            Description
          </label>
          <textarea
            id="recipe-description"
            rows={3}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            className={cn(INPUT, "resize-y py-2")}
          />
        </div>
      </div>
      <References detail={detail} />
      <RecipeTargets
        metrics={metrics}
        targets={targets}
        disabled={patch.isPending}
        onChange={setTargets}
      />
      <div className="flex flex-wrap gap-3">
        <Button
          disabled={!changed || name.trim() === "" || patch.isPending}
          onClick={() => patch.mutate({ name, description, targets })}
        >
          {patch.isPending ? "Saving…" : "Save recipe"}
        </Button>
        <Button variant="outline" asChild>
          <a href={styleRecipeExportUrl(recipe.id)} download>
            <DownloadSimpleIcon aria-hidden />
            Export JSON
          </a>
        </Button>
      </div>
    </section>
  );
}
