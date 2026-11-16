import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import { fileURLToPath } from "node:url";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);
const PIPELINE_TIMEOUT = 180_000;
const PRO_EDIT_TIMEOUT = 180_000;

/** Where screenshot index of this check is saved. */
function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-225-${index}.png`, import.meta.url),
  );
}

/** Where screenshot index of the TASK-236 checks (inbox thumbnail, dialog
 * footer) is saved. */
function fixScreenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-236-${index}.png`, import.meta.url),
  );
}

let projectId: string | undefined;

/** Wait until the project's processing ended. */
async function waitUntilEnded(request: APIRequestContext, id: string) {
  await expect
    .poll(
      async () =>
        (await (await request.get(`/api/projects/${id}`)).json()).status,
      { timeout: PIPELINE_TIMEOUT, intervals: [1000] },
    )
    .toMatch(/^(done|failed)$/);
}

test.afterEach(async ({ request }) => {
  const campaigns = await (await request.get("/api/campaigns")).json();
  for (const { id } of campaigns as { id: number }[]) {
    await request.delete(`/api/campaigns/${id}`);
  }
  if (projectId === undefined) return;
  await request.delete(`/api/projects/${projectId}`);
  projectId = undefined;
});

/** Open the Pro Edit dialog of the gallery's first card. */
async function openDialog(page: Page) {
  await page
    .getByRole("article")
    .first()
    .getByRole("button", { name: "Pro Edit" })
    .click();
  const dialog = page.getByRole("dialog", { name: "Pro Edit" });
  await expect(dialog.getByRole("radio")).toHaveCount(6);
  await expect(dialog.getByLabel("Cost estimate")).not.toHaveText(
    "Estimating the cost…",
  );
  return dialog;
}

test("make a Pro Edit variant from the gallery and approve it in the inbox", async ({
  page,
  request,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + PRO_EDIT_TIMEOUT + 60_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  const created = await request.post("/api/campaigns", {
    data: { name: "Spring clips", rate_per_1k_usd: 1.5 },
  });
  const campaignId = ((await created.json()) as { id: number }).id;

  await page.goto("/");
  await page.getByLabel("Upload a video file").setInputFiles(SAMPLE);
  const settings = page.getByRole("dialog", { name: "Clip settings" });
  await settings.getByLabel("Source rights").selectOption("own");
  await settings.getByRole("button", { name: "Get clips" }).click();
  await expect(page).toHaveURL(/\/projects\/\d+$/);
  projectId = page.url().split("/").pop()!;
  await waitUntilEnded(request, projectId);
  await request.put(`/api/projects/${projectId}/campaign`, {
    data: { campaign_id: campaignId },
  });
  await page.reload();
  const original = page.getByRole("article").first();
  const originalTitle = await original.getAttribute("aria-label");

  // The dialog: presets with their looping previews, the campaign warning.
  let dialog = await openDialog(page);
  await expect(dialog.getByRole("alert")).toContainText(
    "Spring clips does not say whether heavy edits are allowed",
  );
  await dialog.getByText("Phonk Edit", { exact: true }).click();
  await expect(dialog.getByRole("radio", { name: /Phonk Edit/ })).toBeChecked();
  await page.screenshot({ path: screenshot(1), animations: "disabled" });
  // At 1280x720 the options scroll and Cancel / Run Pro Edit stay in view.
  expect(page.viewportSize()).toEqual({ width: 1280, height: 720 });
  for (const name of ["Cancel", "Run Pro Edit"]) {
    await expect(dialog.getByRole("button", { name })).toBeInViewport({
      ratio: 1,
    });
  }
  await page.screenshot({ path: fixScreenshot(2), animations: "disabled" });

  // Run, follow the progress until the variant is ready.
  await dialog.getByRole("button", { name: "Run Pro Edit" }).click();
  await expect(
    dialog.getByRole("list", { name: "Pro Edit steps" }),
  ).toBeVisible();
  await expect(dialog.getByText(/The Pro Edit variant is ready/)).toBeVisible({
    timeout: PRO_EDIT_TIMEOUT,
  });
  await page.screenshot({ path: screenshot(2), animations: "disabled" });
  await page.keyboard.press("Escape");

  // The variant's linked card right after its original.
  const variant = page.getByRole("article", {
    name: `${originalTitle} — Pro Edit`,
  });
  await expect(variant).toBeVisible();
  await expect(variant.getByText("Pro Edit", { exact: true })).toBeVisible();
  await expect(
    variant.getByRole("link", { name: `Pro Edit of “${originalTitle}”` }),
  ).toBeVisible();
  await variant.scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(3), animations: "disabled" });

  // The inbox: the original's draft with its Pro Edit to approve as well.
  const clips = (await (
    await request.get(`/api/projects/${projectId}/clips`)
  ).json()) as { id: number; title: string }[];
  const originalId = clips.find((clip) => clip.title === originalTitle)!.id;
  await request.post("/api/drafts", { data: { clip_id: originalId } });
  await page.goto("/inbox");
  await page.getByRole("tab", { name: /^Needs fix \(1\)$/ }).click();
  const variants = page.getByRole("list", { name: "Pro Edit variants" });
  await expect(variants).toBeVisible();
  await expect(
    variants.getByRole("button", { name: "Approve both" }),
  ).toBeVisible();
  // The variant's thumbnail is its rendered Pro Edit video, loaded (and
  // the original's preview, for the screenshot).
  for (const video of [
    variants.getByLabel(/^Preview of /),
    page.getByLabel(`Preview of ${originalTitle}`, { exact: true }),
  ]) {
    await expect
      .poll(() => video.evaluate((v: HTMLVideoElement) => v.readyState), {
        timeout: 60_000,
      })
      .toBeGreaterThanOrEqual(2);
  }
  await page.screenshot({ path: screenshot(4), animations: "disabled" });
  await page.screenshot({ path: fixScreenshot(1), animations: "disabled" });

  // The same in the dark theme.
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await expect(variants).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: screenshot(5), animations: "disabled" });
  await page.goto(`/projects/${projectId}`);
  await expect(variant).toBeVisible();
  await variant.scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(6), animations: "disabled" });
  dialog = await openDialog(page);
  await page.screenshot({ path: screenshot(7), animations: "disabled" });
  await page.keyboard.press("Escape");

  expect(errors).toEqual([]);
});
