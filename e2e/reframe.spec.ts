import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);
const PIPELINE_TIMEOUT = 180_000;

/** Where the screenshot number index of this check is saved. */
function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-83-${index}.png`, import.meta.url),
  );
}

let projectId: string | undefined;

test.afterEach(async ({ request }) => {
  if (projectId === undefined) return;
  const response = await request.delete(`/api/projects/${projectId}`);
  expect(response.status()).toBe(204);
  projectId = undefined;
});

test("choose a reframe style, then set a custom ratio in the editor", async ({
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
  const style = settings.getByLabel("Reframe style");
  await expect(style.getByRole("option", { name: "Vlog" })).toBeAttached();
  await style.selectOption("vlog");
  await style.scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(1) });
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

  await page
    .getByRole("navigation", { name: "Editor panels" })
    .getByRole("button", { name: "Layout" })
    .click();
  const panel = page.getByRole("complementary", { name: "Layout panel" });
  await expect(panel.getByText(/Reframe style: Vlog/)).toBeVisible();
  await panel.getByLabel("Custom ratio").fill("3:4");
  await panel.getByRole("button", { name: "Set" }).click();
  await expect(
    page.getByRole("button", { name: "Aspect ratio: 3:4 Custom" }),
  ).toBeVisible();
  await page.screenshot({ path: screenshot(2) });

  expect(errors).toEqual([]);
});
