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
    new URL(`../.agent/screenshots/TASK-118-${index}.png`, import.meta.url),
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

test("editor: pick music with its credit, add a sound effect, see them saved", async ({
  page,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 60_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  const clipId = await openEditor(page);
  await page.getByRole("button", { name: "Audio", exact: true }).click();
  const panel = page.getByRole("complementary", { name: "Audio panel" });

  const tracks = panel.getByRole("list", { name: "Music tracks" });
  await expect(tracks.getByRole("listitem").first()).toBeVisible();
  await expect(tracks.getByText(/CC0/).first()).toBeVisible();
  await tracks
    .getByRole("button", { name: /^Use .* as music$/ })
    .first()
    .click();
  await expect(
    panel.getByRole("slider", { name: "Music volume" }),
  ).toBeVisible();
  await page.screenshot({ path: screenshot(1), animations: "disabled" });

  await panel
    .getByRole("list", { name: "Sound effect pack" })
    .getByRole("button", { name: /^Add .* at the playhead$/ })
    .first()
    .click();
  await expect(
    panel.getByRole("list", { name: "Placed sound effects" }),
  ).toBeVisible();

  await panel
    .getByRole("list", { name: "Placed sound effects" })
    .scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(2), animations: "disabled" });

  await page.getByRole("button", { name: "Save changes" }).click();
  await expect
    .poll(async () => {
      const saved = await (
        await page.request.get(`/api/clips/${clipId}`)
      ).json();
      return [saved.tracks.music.length, saved.tracks.sfx.length];
    })
    .toEqual([1, 1]);
  expect(errors).toEqual([]);
});
