import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiUrl } from "@/api/client";
import type {
  StyleMatch,
  StyleMetric,
  StyleRecipe,
  StyleRecipeCreate,
  StyleRecipeDetail,
  StyleRecipeExport,
  StyleRecipePatch,
  StyleTerms,
} from "@/api/types";

const RECIPES = "/proedit/style-recipes";
const recipesKey = ["proedit", "style-recipes"] as const;
const recipeKey = (id: number) => [...recipesKey, id] as const;
const matchKey = (variantId: number) =>
  ["proedit", "style-match", variantId] as const;

/** Every style recipe, oldest first (GET /proedit/style-recipes). */
export function useStyleRecipes() {
  return useQuery({
    queryKey: recipesKey,
    queryFn: () => apiFetch<StyleRecipe[]>(RECIPES),
  });
}

/** Recipe id with its references and targets (GET .../{id}). */
export function useStyleRecipe(id: number | null) {
  return useQuery({
    queryKey: recipeKey(id ?? 0),
    queryFn: () => apiFetch<StyleRecipeDetail>(`${RECIPES}/${id}`),
    enabled: id !== null,
  });
}

/** The metrics of a recipe's targets with their sliders (GET .../metrics);
 * they never change while the app runs. */
export function useStyleMetrics() {
  return useQuery({
    queryKey: [...recipesKey, "metrics"],
    queryFn: () => apiFetch<StyleMetric[]>(`${RECIPES}/metrics`),
    staleTime: Infinity,
  });
}

/** The rights notice and reference limits of the form (GET .../terms). */
export function useStyleTerms() {
  return useQuery({
    queryKey: [...recipesKey, "terms"],
    queryFn: () => apiFetch<StyleTerms>(`${RECIPES}/terms`),
    staleTime: Infinity,
  });
}

/** Store detail as the cached recipe and reload the recipe list (its
 * names and reference counts, and the Pro Edit dialog's choices). */
function useStoreDetail() {
  const queryClient = useQueryClient();
  return (detail: StyleRecipeDetail) => {
    queryClient.setQueryData(recipeKey(detail.recipe.id), detail);
    void queryClient.invalidateQueries({ queryKey: recipesKey, exact: true });
    void queryClient.invalidateQueries({
      queryKey: ["proedit", "choices"],
    });
  };
}

/** Create a recipe from its links (POST /proedit/style-recipes); nothing
 * is downloaded until it is analyzed. */
export function useCreateStyleRecipe() {
  const store = useStoreDetail();
  return useMutation({
    mutationFn: (body: StyleRecipeCreate) =>
      apiFetch<StyleRecipeDetail>(RECIPES, { method: "POST", json: body }),
    onSuccess: store,
  });
}

/** Download and analyze the references of recipe id, then aggregate its
 * targets and describe it (POST .../{id}/analyze; waits until done). */
export function useAnalyzeStyleRecipe(id: number) {
  const store = useStoreDetail();
  return useMutation({
    mutationFn: () =>
      apiFetch<StyleRecipeDetail>(`${RECIPES}/${id}/analyze`, {
        method: "POST",
      }),
    onSuccess: store,
  });
}

/** Save the editor's name, description or targets (PATCH .../{id}). */
export function usePatchStyleRecipe(id: number) {
  const store = useStoreDetail();
  return useMutation({
    mutationFn: (patch: StyleRecipePatch) =>
      apiFetch<StyleRecipeDetail>(`${RECIPES}/${id}`, {
        method: "PATCH",
        json: patch,
      }),
    onSuccess: store,
  });
}

/** Store an exported recipe file as a new recipe (POST .../import). */
export function useImportStyleRecipe() {
  const store = useStoreDetail();
  return useMutation({
    mutationFn: (file: StyleRecipeExport) =>
      apiFetch<StyleRecipeDetail>(`${RECIPES}/import`, {
        method: "POST",
        json: file,
      }),
    onSuccess: store,
  });
}

/** The URL that downloads recipe id as a JSON file. */
export function styleRecipeExportUrl(id: number): string {
  return apiUrl(`${RECIPES}/${id}/export`);
}

/** The last style-match of variant variantId against its plan's recipe,
 * or null when it was not measured since its video changed. */
export function useStyleMatch(variantId: number) {
  return useQuery({
    queryKey: matchKey(variantId),
    queryFn: () =>
      apiFetch<StyleMatch | null>(`/proedit/clips/${variantId}/style-match`, {
        silent: true,
      }),
  });
}

/** Measure the rendered video of variantId against its plan's recipe
 * (POST .../style-match; waits for the analysis). */
export function useMeasureStyleMatch(variantId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<StyleMatch>(`/proedit/clips/${variantId}/style-match`, {
        method: "POST",
      }),
    onSuccess: (match) => queryClient.setQueryData(matchKey(variantId), match),
  });
}
