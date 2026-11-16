import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { turnAutosaveOff } from "./autosave";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);
const PIPELINE_TIMEOUT = 180_000;

let projectId: string | undefined;

test.afterEach(async ({ request }) => {
  if (projectId === undefined) return;
  const response = await request.delete(`/api/projects/${projectId}`);
  expect(response.status()).toBe(204);
  projectId = undefined;
});

/** Where the screenshot number index of this check is saved. */
function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-96-${index}.png`, import.meta.url),
  );
}

/** Upload the fixture, get clips and open the first clip's editor. */
async function openEditor(page: Page) {
  await turnAutosaveOff(page);
  await page.goto("/");
  await page.getByLabel("Upload a video file").setInputFiles(SAMPLE);
  const settings = page.getByRole("dialog", { name: "Clip settings" });
  await settings.getByLabel("Source rights").selectOption("own");
  await settings.getByRole("button", { name: "Get clips" }).click();
  await expect(page).toHaveURL(/\/projects\/\d+$/);
  projectId = page.url().split("/").pop();
  // The heading shows once the pipeline is done (its clips are final).
  await expect(
    page.getByRole("heading", { name: /^Clips \(\d+\)$/ }),
  ).toBeVisible({ timeout: PIPELINE_TIMEOUT });
  await page
    .getByRole("article")
    .first()
    .getByRole("link", { name: "Edit clip" })
    .click();
}

test("captions v2: preview, word marks, gallery and saved word color", async ({
  page,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 60_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  await openEditor(page);
  await page
    .getByRole("navigation", { name: "Editor panels" })
    .getByRole("button", { name: "Captions" })
    .click();
  const panel = page.getByRole("complementary", { name: "Captions panel" });
  await expect(panel.getByAltText(/caption preview/i)).toBeVisible({
    timeout: 30_000,
  });
  await panel.getByAltText(/caption preview/i).scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(1), animations: "disabled" });

  await panel
    .getByRole("button", { name: /^Edit word at / })
    .first()
    .click();
  const popover = page.getByRole("dialog", { name: /^Word "/ });
  await popover.getByRole("button", { name: "🔥" }).click();
  await popover.getByLabel("Word color").fill("#22c55e");
  await page.screenshot({ path: screenshot(2), animations: "disabled" });
  await page.keyboard.press("Escape");

  await panel.getByRole("button", { name: "All templates" }).click();
  const gallery = page.getByRole("dialog", { name: "Caption templates" });
  await expect(gallery.getByRole("radio")).toHaveCount(30);
  await page.screenshot({ path: screenshot(3), animations: "disabled" });
  await page.keyboard.press("Escape");

  const patched = page.waitForResponse(
    (response) =>
      response.request().method() === "PATCH" &&
      /\/api\/clips\/\d+$/.test(response.url()),
  );
  await page.getByRole("button", { name: "Save changes" }).click();
  expect((await patched).status()).toBe(200);
  const clipId = page.url().split("/").pop();
  const saved = await (await page.request.get(`/api/clips/${clipId}`)).json();
  expect(saved.caption_style.word_marks).toContainEqual(
    expect.objectContaining({
      emoji: "🔥",
      color: "#22c55e",
      source: "user",
    }),
  );

  await panel.getByRole("button", { name: "Vocabulary" }).click();
  await panel.getByRole("button", { name: "Brand vocabulary" }).click();
  await expect(
    page.getByRole("dialog", { name: "Brand vocabulary" }).getByLabel("Terms"),
  ).toBeVisible();
  await page.screenshot({ path: screenshot(4), animations: "disabled" });

  expect(errors).toEqual([]);
});
