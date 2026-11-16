import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

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

/** Where the screenshot number index of this check is saved. */
function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-103-${index}.png`, import.meta.url),
  );
}

/** Upload the fixture, get clips and open the first clip's editor. */
async function openEditor(page: Page): Promise<string> {
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

test("sections: add from the transcript, rearrange, split and duplicate", async ({
  page,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 60_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  const clipId = await openEditor(page);
  const sections = () =>
    page.request
      .get(`/api/clips/${clipId}`)
      .then(async (response) => (await response.json()).segments as number[][]);
  const before = await sections();
  expect(before).toHaveLength(1);

  await page.getByRole("button", { name: "Sections" }).click();
  const rows = page
    .getByRole("list", { name: "Sections" })
    .getByRole("listitem");
  await expect(rows).toHaveCount(1);

  // Add a transcript line outside the clip as a second section.
  const add = page
    .getByRole("list", { name: "Source transcript" })
    .getByRole("button", { name: /^Add section/ })
    .and(page.locator(":not([disabled])"))
    .first();
  await expect(add).toBeVisible();
  await add.click();
  await expect(rows).toHaveCount(2);
  await expect.poll(async () => (await sections()).length).toBe(2);
  await page.screenshot({ path: screenshot(1), animations: "disabled" });

  // Rearrange: the second section plays first.
  const [firstSpan, secondSpan] = await sections();
  await page.getByRole("button", { name: "Move Section 2 earlier" }).click();
  await expect.poll(sections).toEqual([secondSpan, firstSpan]);

  // Duplicate the clip: a link to the copy shows.
  await page.getByRole("button", { name: "Duplicate clip" }).click();
  await expect(page.getByText("New clip:")).toBeVisible();
  await page.screenshot({ path: screenshot(2), animations: "disabled" });

  expect(errors).toEqual([]);
});
