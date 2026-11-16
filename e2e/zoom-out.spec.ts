import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { turnAutosaveOff } from "./autosave";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);
const PIPELINE_TIMEOUT = 180_000;

/** Where the screenshot number index of this check is saved. */
function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-198b-${index}.png`, import.meta.url),
  );
}

let projectId: string | undefined;

test.afterEach(async ({ request }) => {
  if (projectId === undefined) return;
  const response = await request.delete(`/api/projects/${projectId}`);
  expect(response.status()).toBe(204);
  projectId = undefined;
});

test("zoom-out moments in the settings, a segment override and the reframe panel", async ({
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
  await settings.getByRole("radio", { name: "Frequent" }).click();
  await expect(
    settings.getByRole("radio", { name: "Frequent" }),
  ).toHaveAttribute("aria-checked", "true");
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
    .getByLabel("Segments")
    .getByRole("button", { name: /^Segment / })
    .first()
    .click();
  const override = page.getByRole("radiogroup", { name: "Segment layout" });
  await override.getByRole("radio", { name: "Square" }).click();
  await expect(override.getByRole("radio", { name: "Square" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  // The 2.5 s chip is ~47 px wide next to the lane labels, too narrow for
  // the "Square" label (TimelineSegments labelFits): zoom in to read it.
  const zoomIn = page.getByRole("button", { name: "Zoom in (+)" });
  await zoomIn.click();
  await zoomIn.click();
  await expect(
    page
      .getByLabel("Segments")
      .getByRole("button", { name: /^Segment / })
      .first(),
  ).toHaveText("Square");
  await page.screenshot({ path: screenshot(2) });
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(
    page.getByRole("button", { name: "Save changes" }),
  ).toBeDisabled();

  await page
    .getByRole("navigation", { name: "Editor panels" })
    .getByRole("button", { name: "Layout" })
    .click();
  const panel = page.getByRole("complementary", { name: "Layout panel" });
  await expect(panel.getByRole("radio", { name: "Frequent" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  await panel.getByRole("radio", { name: "Subtle" }).click();
  await expect(panel.getByRole("radio", { name: "Subtle" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  await page.screenshot({ path: screenshot(3) });

  expect(errors).toEqual([]);
});
