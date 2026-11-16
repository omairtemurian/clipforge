import { expect, test, type Locator, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { turnAutosaveOff } from "./autosave";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);
const PIPELINE_TIMEOUT = 180_000;

/** Where the screenshot number index of this check is saved. */
function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-88-${index}.png`, import.meta.url),
  );
}

/** Drag box by dx pixels to the right with the mouse. */
async function dragRight(page: Page, box: Locator, dx: number) {
  const bounds = await box.boundingBox();
  if (!bounds) throw new Error("the box is not visible");
  const x = bounds.x + bounds.width / 2;
  const y = bounds.y + bounds.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx / 2, y, { steps: 4 });
  await page.mouse.move(x + dx, y, { steps: 4 });
  await page.mouse.up();
}

let projectId: string | undefined;

test.afterEach(async ({ request }) => {
  if (projectId === undefined) return;
  const response = await request.delete(`/api/projects/${projectId}`);
  expect(response.status()).toBe(204);
  projectId = undefined;
});

test("default layout, layout picker, facecam box and crop keyframes", async ({
  page,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 60_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  await turnAutosaveOff(page);
  await page.goto("/");
  await page.getByLabel("Upload a video file").setInputFiles(SAMPLE);
  const settings = page.getByRole("dialog", { name: "Clip settings" });
  await settings.getByLabel("Source rights").selectOption("own");
  await settings.getByLabel("Default layout").selectOption("screenshare");
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
  const screenshare = panel.getByRole("radio", {
    name: "Screenshare + facecam",
  });
  await expect(screenshare).toHaveAttribute("aria-checked", "true");

  await page.getByRole("button", { name: "Crop", exact: true }).click();
  const facecam = page.getByRole("group", { name: "Facecam box" });
  await expect(facecam).toBeVisible();
  await dragRight(page, facecam, 40);
  await expect(page.getByText(/Your facecam box/)).toBeVisible();
  await page.screenshot({ path: screenshot(1) });

  await panel.getByRole("radio", { name: "Fixed" }).click();
  const window = page.getByRole("group", { name: "Crop window" });
  await expect(window).toBeVisible();
  await dragRight(page, window, 60);
  await expect(page.getByText(/^Keyframe at /)).toBeVisible();
  await expect(
    page.getByLabel("Keyframes").getByRole("button").first(),
  ).toBeVisible();
  await page.screenshot({ path: screenshot(2) });

  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(
    page.getByRole("button", { name: "Save changes" }),
  ).toBeDisabled();

  expect(errors).toEqual([]);
});
