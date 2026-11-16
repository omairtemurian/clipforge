import { expect, type Page } from "@playwright/test";

/** Turn the editor's autosave off for page (before it loads), for checks
 * that save with "Save changes" themselves. */
export async function turnAutosaveOff(page: Page): Promise<void> {
  await page.addInitScript(() =>
    window.localStorage.setItem("clipforge.autosave", "off"),
  );
}

/** Click the editor's "Save changes" and wait for its PATCH requests to
 * answer 200: the clip's (PATCH /clips/{id}) and, with tracks, then the layer
 * tracks' (PATCH /clips/{id}/tracks). The button is also disabled while the
 * save is still in flight, so toBeDisabled alone does not mean saved. */
export async function saveChanges(
  page: Page,
  { tracks = false }: { tracks?: boolean } = {},
): Promise<void> {
  const patched = (path: RegExp) =>
    page.waitForResponse(
      (response) =>
        response.request().method() === "PATCH" &&
        path.test(new URL(response.url()).pathname),
    );
  const responses = [patched(/^\/api\/clips\/\d+$/)];
  if (tracks) responses.push(patched(/^\/api\/clips\/\d+\/tracks$/));
  await page.getByRole("button", { name: "Save changes" }).click();
  for (const response of await Promise.all(responses)) {
    expect(response.status()).toBe(200);
  }
}
