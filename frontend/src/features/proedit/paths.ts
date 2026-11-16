import { apiUrl } from "@/api/client";

/** The route of a clip's Pro Edit page, inside the app shell. */
export const PRO_EDIT_ROUTE = "clips/:clipId/proedit";

/** The URL of clip clipId's Pro Edit page, with variant variantId open in
 * its editor if given. */
export function proEditPath(clipId: number, variantId?: number): string {
  const path = `/clips/${clipId}/proedit`;
  return variantId === undefined ? path : `${path}?variant=${variantId}`;
}

/** The route of the style recipes page, inside the app shell. */
export const STYLE_RECIPES_ROUTE = "proedit/style-recipes";

/** The URL of the style recipes page, with recipe recipeId open if given. */
export function styleRecipesPath(recipeId?: number): string {
  const path = `/${STYLE_RECIPES_ROUTE}`;
  return recipeId === undefined ? path : `${path}?recipe=${recipeId}`;
}

/** The URL of Pro Edit variant variantId's rendered video (GET
 * /proedit/clips/{id}/video), versioned by version so a new render loads
 * again. */
export function variantVideoUrl(variantId: number, version: string): string {
  return apiUrl(
    `/proedit/clips/${variantId}/video?v=${encodeURIComponent(version)}`,
  );
}
