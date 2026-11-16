import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { turnAutosaveOff } from "./autosave";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);
const PIPELINE_TIMEOUT = 180_000;

test.use({ viewport: { width: 1440, height: 900 } });

let projectId: string | undefined;

test.afterEach(async ({ request }) => {
  if (projectId === undefined) return;
  const response = await request.delete(`/api/projects/${projectId}`);
  expect(response.status()).toBe(204);
  projectId = undefined;
});

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-110-${index}.png`, import.meta.url),
  );
}

/** Upload the fixture, get clips and open the first clip's editor. */
async function openEditor(page: Page): Promise<string> {
  await turnAutosaveOff(page);
  await page.goto("/");
  await page.getByLabel("Upload a video file").setInputFiles(SAMPLE);
  const settings = page.getByRole("dialog", { name: "Clip settings" });
  await settings.getByLabel("Source rights").selectOption("own");
  await settings.getByRole("button", { name: "Get clips" }).click();
  await expect(page).toHaveURL(/\/projects\/\d+$/);
  projectId = page.url().split("/").pop();
  await expect(
    page.getByRole("heading", { name: /^Clips \(\d+\)$/ }),
  ).toBeVisible({ timeout: PIPELINE_TIMEOUT });
  await page
    .getByRole("article")
    .first()
    .getByRole("link", { name: "Edit clip" })
    .click();
  await expect(page).toHaveURL(/\/clips\/\d+$/);
  return page.url().split("/").pop()!;
}

test("editor: add a hook and a headline, open the graphics panel", async ({
  page,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 60_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  const clipId = await openEditor(page);

  // Hooks: a template with the opening words of the captions.
  await page.getByRole("button", { name: "Hooks", exact: true }).click();
  await page.getByRole("button", { name: /Slow Push/ }).click();
  await page.getByRole("button", { name: "Add hook" }).click();
  const hookText = page.getByLabel("Hook text", { exact: true });
  await expect(hookText).not.toHaveValue("");
  await hookText.fill("Wait for it");
  await page.getByRole("button", { name: "Save text" }).click();
  await expect(page.getByRole("button", { name: "Save text" })).toBeDisabled();

  // Headline: typed text becomes a text item on the timeline.
  await page.getByLabel("Headline text").fill("He ate it all");
  await page.getByRole("button", { name: "Set headline" }).click();
  await expect(
    page
      .getByRole("group", { name: "Text track" })
      .getByRole("button", { name: /^Text: He ate it all,/ }),
  ).toBeVisible();
  await page.screenshot({ path: screenshot(1), animations: "disabled" });

  // Graphics: nothing found yet.
  await page.getByRole("button", { name: "Graphics", exact: true }).click();
  await expect(page.getByText("No motion graphics")).toBeVisible();
  await page.screenshot({ path: screenshot(2), animations: "disabled" });

  const saved = await (await page.request.get(`/api/clips/${clipId}`)).json();
  expect(saved.hook).toMatchObject({
    template: "slow_push",
    text: "Wait for it",
  });
  expect(saved.hook_text).toBe("He ate it all");
  expect(saved.tracks.text[0].id).toBe("headline");
  expect(errors).toEqual([]);
});
