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
    new URL(`../.agent/screenshots/TASK-114-${index}.png`, import.meta.url),
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

test("editor: review and apply speech cleanup, set the enhancement strength", async ({
  page,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 60_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  const clipId = await openEditor(page);
  const before = await (await page.request.get(`/api/clips/${clipId}`)).json();

  await page.getByRole("button", { name: "Cleanup", exact: true }).click();
  await page.getByRole("button", { name: "Find what to remove" }).click();
  const list = page.getByRole("list", { name: "What will be removed" });
  await expect(list).toBeVisible();
  const boxes = list.getByRole("checkbox");
  const found = await boxes.count();
  expect(found).toBeGreaterThan(1);
  await boxes.first().uncheck();
  await page.screenshot({ path: screenshot(1), animations: "disabled" });

  await page
    .getByRole("button", { name: new RegExp(`^Remove ${found - 1} cuts?$`) })
    .click();
  await expect(list).toBeHidden();

  const slider = page.getByRole("slider", { name: "Enhancement strength" });
  await slider.focus();
  await slider.press("End");
  await expect(page.getByText("100%")).toBeVisible();
  await page.screenshot({ path: screenshot(2), animations: "disabled" });

  await expect
    .poll(async () => {
      const saved = await (
        await page.request.get(`/api/clips/${clipId}`)
      ).json();
      return saved.enhance;
    })
    .toBe(1);
  const saved = await (await page.request.get(`/api/clips/${clipId}`)).json();
  expect(saved.cut_ranges).not.toEqual(before.cut_ranges);
  expect(errors).toEqual([]);
});
