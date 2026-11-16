import { SwatchesIcon } from "@phosphor-icons/react";
import { Navigate, useSearchParams } from "react-router-dom";
import type { StyleRecipe, StyleRecipeDetail } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { choiceClass, pageColumn } from "@/lib/surfaces";
import { cn } from "@/lib/utils";
import { useProEditEnabled } from "./api";
import { RecipeEditor } from "./RecipeEditor";
import { useStyleMetrics, useStyleRecipe, useStyleRecipes } from "./styleApi";
import { ImportRecipeButton, StyleRecipeForm } from "./StyleRecipeForm";

/** The recipes to pick from, the chosen one marked. */
function RecipeList({
  recipes,
  selected,
  onSelect,
}: {
  recipes: StyleRecipe[];
  selected: number | null;
  onSelect: (id: number) => void;
}) {
  if (recipes.length === 0) {
    return (
      <p className="text-body text-muted-foreground">
        No style recipe yet: create one from reference links or import a recipe
        file.
      </p>
    );
  }
  return (
    <ul aria-label="Style recipes" className="flex flex-col gap-2">
      {recipes.map((recipe) => (
        <li key={recipe.id}>
          <button
            type="button"
            aria-current={recipe.id === selected ? "true" : undefined}
            onClick={() => onSelect(recipe.id)}
            className={cn(
              choiceClass(recipe.id === selected),
              "w-full text-left",
            )}
          >
            <span className="block text-body font-medium">{recipe.name}</span>
            <span className="text-caption text-muted-foreground">
              {recipe.reference_count} reference
              {recipe.reference_count === 1 ? "" : "s"}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/** The editor of recipe id once it and the metrics are loaded. */
function SelectedRecipe({ id }: { id: number | null }) {
  const detail = useStyleRecipe(id);
  const metrics = useStyleMetrics();
  if (id === null) {
    return (
      <EmptyState icon={SwatchesIcon} title="Pick a style recipe">
        Its targets show here as sliders: the numbers a Pro Edit with this
        recipe aims for and its style-match is scored against.
      </EmptyState>
    );
  }
  if (detail.isError) {
    return (
      <p className="text-body text-muted-foreground">
        Could not load this recipe.
      </p>
    );
  }
  if (!detail.data || !metrics.data) {
    return <Skeleton className="h-64 rounded-xl" />;
  }
  return (
    <RecipeEditor
      key={JSON.stringify([detail.data.recipe, detail.data.targets])}
      detail={detail.data}
      metrics={metrics.data}
    />
  );
}

/** The page of a Pro Edit enabled app. */
function StyleRecipesPage() {
  const [params, setParams] = useSearchParams();
  const recipes = useStyleRecipes();
  const selected = Number(params.get("recipe")) || null;
  const select = (id: number) => setParams({ recipe: String(id) });
  const open = (detail: StyleRecipeDetail) => select(detail.recipe.id);
  return (
    <>
      <PageHeader
        title="Style recipes"
        width="wide"
        description="Reference videos measured into targets a Pro Edit aims for. Edit them, import or export them as JSON."
        actions={<ImportRecipeButton onImported={open} />}
      />
      <div
        className={cn(
          pageColumn("wide"),
          "grid gap-8 pb-section lg:grid-cols-[18rem_1fr]",
        )}
      >
        <div className="flex flex-col gap-8">
          {recipes.data ? (
            <RecipeList
              recipes={recipes.data}
              selected={selected}
              onSelect={select}
            />
          ) : (
            <Skeleton className="h-24 rounded-xl" />
          )}
          <StyleRecipeForm onCreated={open} />
        </div>
        <SelectedRecipe id={selected} />
      </div>
    </>
  );
}

/**
 * The route /proedit/style-recipes (SPEC-v3 4.4-4.5): the style recipes
 * with the editor of the one chosen (?recipe=id), the form of a new one
 * and the import of a recipe file. While Pro Edit is off it goes Home.
 */
export function StyleRecipesRoute() {
  const proEdit = useProEditEnabled();
  if (proEdit.pending) {
    return (
      <div className={cn(pageColumn(), "pt-section")}>
        <Skeleton className="h-24 rounded-xl" />
      </div>
    );
  }
  if (!proEdit.enabled) return <Navigate to="/" replace />;
  return <StyleRecipesPage />;
}
