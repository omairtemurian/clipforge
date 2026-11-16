import { expect, test } from "@playwright/test";
import { readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import {
  PIPELINE_TIMEOUT,
  PRO_EDIT_TIMEOUT,
  postingCampaign,
  roomiestItem,
  runProEdit,
  uploadSample,
  watchErrors,
} from "./proedit-flow";

// The Pro Edit end to end (SPEC-v3 7): a clip's Skull Moment Pro variant
// followed through its progress, edited on its EDL lanes, rendered again
// and approved from the inbox; and a style recipe made from 2 reference
// links, analyzed, applied to a Pro Edit and measured. Test mode cannot
// reach a video site, so the links point at its stand-in
// (/api/testmode/style-references/<name>.mp4, the fixture video): the real
// fetch, analysis and media deletion run against this machine only.

const ANALYZE_TIMEOUT = 120_000;
const REFERENCES = ["night-a", "night-b"].map(
  (name) => `http://127.0.0.1:8000/api/testmode/style-references/${name}.mp4`,
);
// The test server's data dir (playwright.config.ts: .run/data).
const WORK_DIR = fileURLToPath(new URL("./.run/data/work", import.meta.url));

interface Run {
  id: number;
  plan_id: number | null;
  status: string;
  mode: string;
}

/** Where screenshot index of this check (of task, default TASK-235) is
 * saved. */
function screenshot(index: number, task = 235): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-${task}-${index}.png`, import.meta.url),
  );
}

let projectId: string | undefined;
let accountId: number | undefined;

test.afterEach(async ({ request }) => {
  const posts = (await (await request.get("/api/posts")).json()) as {
    id: number;
    status: string;
  }[];
  for (const post of posts.filter((p) => p.status === "queued")) {
    await request.post(`/api/posts/${post.id}/cancel`);
  }
  const campaigns = await (await request.get("/api/campaigns")).json();
  for (const { id } of campaigns as { id: number }[]) {
    await request.delete(`/api/campaigns/${id}`);
  }
  if (accountId !== undefined)
    await request.delete(`/api/accounts/${accountId}`);
  if (projectId !== undefined)
    await request.delete(`/api/projects/${projectId}`);
  projectId = accountId = undefined;
});

test("Skull Moment Pro: progress, side by side, move an item, render again, approve the variant", async ({
  page,
  request,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 2 * PRO_EDIT_TIMEOUT + 60_000);
  const errors = watchErrors(page);
  const posting = await postingCampaign(request);
  const { campaignId } = posting;
  accountId = posting.accountId;
  const uploaded = await uploadSample(page, request);
  projectId = uploaded.projectId;
  const { originalId } = uploaded;
  await request.put(`/api/projects/${projectId}/campaign`, {
    data: { campaign_id: campaignId },
  });
  await page.reload();

  // The run: its steps while it works, then the ready variant.
  const dialog = await runProEdit(page, "Skull Moment", {
    index: 2,
    label: "Pro",
  });
  const steps = dialog.getByRole("list", { name: "Pro Edit steps" });
  await expect(steps.getByRole("listitem")).toHaveText([
    "Plan",
    "Proxy",
    /^Critic round \d\/\d$/,
    "Final render",
  ]);
  await expect(steps.locator('[data-state="running"]')).toHaveCount(1);
  await page.screenshot({ path: screenshot(1), animations: "disabled" });
  await expect(dialog.getByText(/The Pro Edit variant is ready/)).toBeVisible({
    timeout: PRO_EDIT_TIMEOUT,
  });
  // What post-processing moved or dropped (TASK-237), one line each.
  const notes = dialog.getByRole("region", { name: "Edit notes" });
  await expect(notes).toBeVisible();
  await notes.scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(1, 237), animations: "disabled" });
  await dialog.getByRole("link", { name: "Open Pro Edit variants" }).click();

  // Side by side: the original and its Pro Edit, both decoding frames.
  await expect(page).toHaveURL(/\/clips\/\d+\/proedit\?variant=\d+$/);
  const variantId = Number(new URL(page.url()).searchParams.get("variant"));
  for (const label of ["Original preview", "Pro Edit preview"]) {
    await expect
      .poll(
        () =>
          page
            .getByLabel(label)
            .evaluate((v: HTMLVideoElement) => v.videoWidth),
        { timeout: 60_000 },
      )
      .toBeGreaterThan(0);
  }
  await expect(page.getByLabel("Plan version")).toHaveText("Plan v1");

  // Move the zoom item with the most room after it to the right: plan v2.
  const lanes = page.getByRole("region", { name: "EDL lanes" });
  await lanes.scrollIntoViewIfNeeded();
  const zoom = lanes.getByRole("group", { name: "Zoom lane" });
  const { x, y, room } = await roomiestItem(zoom);
  expect(room).toBeGreaterThan(30);
  const patched = page.waitForResponse(
    (res) =>
      res.request().method() === "PATCH" &&
      res.url().endsWith(`/api/proedit/clips/${variantId}/plan`),
  );
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 10, y, { steps: 2 });
  await page.mouse.move(x + Math.min(room / 2, 80), y, { steps: 8 });
  await page.mouse.up();
  const saved = await patched;
  expect(saved.status(), await saved.text()).toBe(200);
  await expect(page.getByLabel("Plan version")).toContainText("Plan v2");
  await expect(
    lanes.locator('[data-testid="edl-item"][data-source="manual"]'),
  ).toHaveCount(1);
  await page.screenshot({ path: screenshot(2), animations: "disabled" });

  // Render plan v2: its render run ends and the button goes away.
  await page.getByRole("button", { name: "Render plan v2" }).click();
  const runs = async () =>
    (await (
      await request.get(`/api/proedit/clips/${variantId}/runs`)
    ).json()) as Run[];
  await expect
    .poll(
      async () =>
        (await runs()).filter((r) => r.mode === "render").map((r) => r.status),
      { timeout: PRO_EDIT_TIMEOUT, intervals: [1000] },
    )
    .toEqual(["done"]);
  const plan = (await (
    await request.get(`/api/proedit/clips/${variantId}/plan`)
  ).json()) as { id: number; version: number };
  expect(plan.version).toBe(2);
  expect((await runs()).find((r) => r.mode === "render")!.plan_id).toBe(
    plan.id,
  );
  await expect(page.getByText("· a job is running")).toBeHidden();
  await expect(
    page.getByRole("button", { name: "Render plan v2" }),
  ).toBeHidden();
  await page.screenshot({ path: screenshot(3), animations: "disabled" });

  // The inbox: approve the Pro Edit variant under its original's draft.
  await request.post("/api/drafts", { data: { clip_id: originalId } });
  await page.goto("/inbox");
  const variants = page.getByRole("list", { name: "Pro Edit variants" });
  await expect(variants).toBeVisible();
  await variants.getByRole("button", { name: "Approve Pro Edit" }).click();
  await expect(
    page.getByText(/^Pro Edit — Approved: 1 post scheduled for/),
  ).toBeVisible();
  await page.screenshot({ path: screenshot(4), animations: "disabled" });
  const drafts = (await (
    await request.get(`/api/drafts?campaign_id=${campaignId}`)
  ).json()) as { clip_id: number; status: string }[];
  expect(drafts.find((d) => d.clip_id === variantId)?.status).toBe("approved");
  expect(drafts.find((d) => d.clip_id === originalId)?.status).not.toBe(
    "approved",
  );
  const posts = (await (await request.get("/api/posts")).json()) as {
    clip_id: number;
    status: string;
  }[];
  expect(
    posts.filter((p) => p.status === "queued").map((p) => p.clip_id),
  ).toEqual([variantId]);
  expect(errors).toEqual([]);
});

test("a style recipe from 2 links, applied to a Pro Edit, gives a style-match score", async ({
  page,
  request,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + ANALYZE_TIMEOUT + 2 * PRO_EDIT_TIMEOUT);
  const errors = watchErrors(page);

  // Create the recipe from the 2 links and analyze them.
  await page.goto("/proedit/style-recipes");
  const form = page.getByRole("form", { name: "New style recipe" });
  await form.getByLabel("Name").fill("Night references");
  await form.getByLabel(/^Reference links/).fill(REFERENCES.join("\n"));
  await form.getByLabel(/I have the right to analyze/).check();
  await form.getByRole("button", { name: "Create recipe" }).click();
  const editor = page.getByRole("region", { name: "Recipe Night references" });
  const references = editor.getByRole("region", { name: "References" });
  await expect(references.getByText("Not analyzed yet")).toHaveCount(2);
  await references.getByRole("button", { name: "Analyze references" }).click();
  await expect(references.getByText("Analyzed (media deleted)")).toHaveCount(
    2,
    { timeout: ANALYZE_TIMEOUT },
  );
  await expect(
    editor.getByRole("slider", { name: "Cuts", exact: true }),
  ).toBeVisible();
  const left = await readdir(WORK_DIR).catch(() => [] as string[]);
  expect(left.filter((name) => name.startsWith("style_"))).toEqual([]);
  await page.screenshot({
    path: screenshot(5),
    fullPage: true,
    animations: "disabled",
  });

  // Apply it: a Pro Edit of a clip with the recipe, then measure the match.
  const uploaded = await uploadSample(page, request);
  projectId = uploaded.projectId;
  const dialog = await runProEdit(
    page,
    "Phonk Edit",
    { index: 1, label: "Standard" },
    "Night references",
  );
  await expect(dialog.getByText(/The Pro Edit variant is ready/)).toBeVisible({
    timeout: PRO_EDIT_TIMEOUT,
  });
  // What post-processing moved or dropped (TASK-237), one line each.
  const notes = dialog.getByRole("region", { name: "Edit notes" });
  await expect(notes).toBeVisible();
  await notes.scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(1, 237), animations: "disabled" });
  await dialog.getByRole("link", { name: "Open Pro Edit variants" }).click();
  const match = page.getByRole("region", { name: "Style match" });
  await match.scrollIntoViewIfNeeded();
  await match.getByRole("button", { name: "Measure" }).click();
  await expect(match.getByText(/^\d{1,3}\/100$/)).toBeVisible({
    timeout: ANALYZE_TIMEOUT,
  });
  await expect(
    match.getByRole("link", { name: "Night references" }),
  ).toBeVisible();
  await expect(
    match.getByRole("list", { name: "Style metrics" }).getByRole("listitem"),
  ).not.toHaveCount(0);
  await page.screenshot({
    path: screenshot(6),
    fullPage: true,
    animations: "disabled",
  });
  expect(errors).toEqual([]);
});
