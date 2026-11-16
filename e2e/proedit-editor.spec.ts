import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";
import {
  PIPELINE_TIMEOUT,
  PRO_EDIT_TIMEOUT,
  uploadAndMakeVariant,
} from "./proedit-flow";

/** Where screenshot index of this check is saved. */
function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-226-${index}.png`, import.meta.url),
  );
}

let projectId: string | undefined;

test.afterEach(async ({ request }) => {
  if (projectId === undefined) return;
  await request.delete(`/api/projects/${projectId}`);
  projectId = undefined;
});

test("edit a Pro Edit variant's plan on its EDL lanes", async ({
  page,
  request,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + PRO_EDIT_TIMEOUT + 60_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  const ids = await uploadAndMakeVariant(page, request);
  projectId = ids.projectId;
  const { originalId, variantId } = ids;

  // The editor: both previews, the plan's items on their lanes.
  await page.goto(`/clips/${originalId}/proedit`);
  const lanes = page.getByRole("region", { name: "EDL lanes" });
  await expect(lanes).toBeVisible();
  const original = page.getByLabel("Original preview");
  const proEdit = page.getByLabel("Pro Edit preview");
  await expect(original).toBeVisible();
  await expect(proEdit).toBeVisible();
  await expect(page.getByLabel("Plan version")).toHaveText("Plan v1");

  // The original's preview (rendered on its first request) loads a frame.
  await expect(original).toHaveAttribute(
    "src",
    /\/api\/clips\/\d+\/preview\?v=/,
  );
  await expect
    .poll(() => original.evaluate((v: HTMLVideoElement) => v.videoWidth), {
      timeout: 60_000,
    })
    .toBeGreaterThan(0);
  await expect(page.getByText("Making the preview…")).toBeHidden();

  // Play both: the two previews advance together.
  await page.getByRole("button", { name: "Play both" }).click();
  const times = () =>
    Promise.all(
      [original, proEdit].map((video) =>
        video.evaluate((v: HTMLVideoElement) => v.currentTime),
      ),
    );
  await expect.poll(async () => (await times())[1]).toBeGreaterThan(1);
  const [left, right] = await times();
  expect(left).toBeGreaterThan(0.5);
  expect(Math.abs(left - right)).toBeLessThan(0.5);
  await page.getByRole("button", { name: "Pause" }).click();
  await expect(page.getByRole("button", { name: "Play both" })).toBeVisible();
  const item = lanes
    .getByRole("group", { name: "Zoom lane" })
    .getByTestId("edl-item")
    .nth(1);
  await expect(item).toBeVisible();
  await page.screenshot({ path: screenshot(1), animations: "disabled" });

  // Drag one item to the right: the guide shows, the drop is PATCHed.
  await lanes.scrollIntoViewIfNeeded();
  const box = (await item.boundingBox())!;
  const area = (await lanes.getByRole("group").first().boundingBox())!;
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  const to = x + area.width / 20;
  const patched = page.waitForRequest(
    (req) =>
      req.method() === "PATCH" &&
      req.url().endsWith(`/api/proedit/clips/${variantId}/plan`),
  );
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 10, y, { steps: 2 });
  await page.mouse.move(to, y, { steps: 8 });
  await expect(
    lanes.getByRole("status").or(lanes.getByLabel("Selected item")),
  ).toBeVisible();
  await page.screenshot({ path: screenshot(2), animations: "disabled" });
  await page.mouse.up();
  const sent = (await patched).postDataJSON() as {
    items: { t_start: number }[];
  };
  expect(sent.items.length).toBeGreaterThan(0);
  await expect(page.getByLabel("Plan version")).toContainText("Plan v2");
  await expect(
    lanes.locator('[data-testid="edl-item"][data-source="manual"]'),
  ).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "Render plan v2" }),
  ).toBeVisible();
  await page.screenshot({ path: screenshot(3), animations: "disabled" });

  // The same in the dark theme.
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.screenshot({ path: screenshot(4), animations: "disabled" });

  expect(errors).toEqual([]);
});
