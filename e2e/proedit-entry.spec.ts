import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);
const PIPELINE_TIMEOUT = 180_000;

/** Where the screenshot number index of this check is saved. */
function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-202-${index}.png`, import.meta.url),
  );
}

let projectId: string | undefined;

test.afterEach(async ({ request }) => {
  if (projectId === undefined) return;
  const response = await request.delete(`/api/projects/${projectId}`);
  expect(response.status()).toBe(204);
  projectId = undefined;
});

test("the editor opens a clip's Pro Edit dialog, which links to its page", async ({
  page,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 60_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

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
  await expect(page.getByRole("article")).toHaveCount(0);
  const entry = page.getByRole("button", { name: "Pro Edit" });
  await expect(entry).toBeVisible();
  await page.screenshot({ path: screenshot(1) });
  await entry.click();
  await page
    .getByRole("dialog", { name: "Pro Edit" })
    .getByRole("link", { name: "See this clip's Pro Edit variants" })
    .click();

  await expect(page).toHaveURL(/\/clips\/\d+\/proedit$/);
  await expect(page.getByRole("heading", { name: "Pro Edit" })).toBeVisible();
  await expect(page.getByText("No Pro Edit variant yet")).toBeVisible();
  await page.screenshot({ path: screenshot(2) });
  await page.getByRole("link", { name: "Back to the clip" }).click();
  await expect(page).toHaveURL(/\/clips\/\d+$/);

  expect(errors).toEqual([]);
});
