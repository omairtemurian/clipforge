import { expect, test, type APIRequestContext } from "@playwright/test";
import { fileURLToPath } from "node:url";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);
const PIPELINE_TIMEOUT = 180_000;
// A 1x1 PNG: the API only checks the image's magic bytes.
const PROOF = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-184-${index}.png`, import.meta.url),
  );
}

interface Draft {
  id: number;
  clip_id: number;
  status: string;
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
  await waitUntilEnded(request, projectId);
  await request.delete(`/api/projects/${projectId}`);
  projectId = undefined;
});

test("approve, reject and fix the autopilot's drafts in the Approval inbox", async ({
  page,
  request,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 120_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  const created = await request.post("/api/campaigns", {
    data: {
      name: "Spring clips",
      creator_name: "Afro",
      allowed_platforms: ["youtube"],
      rate_per_1k_usd: 1.5,
      permission_source_url: "https://example.com/permission",
    },
  });
  const campaignId = ((await created.json()) as { id: number }).id;
  await request.post(`/api/campaigns/${campaignId}/permission-screenshot`, {
    multipart: {
      file: { name: "proof.png", mimeType: "image/png", buffer: PROOF },
    },
  });

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
  const clips = (await (
    await request.get(`/api/projects/${projectId}/clips`)
  ).json()) as { id: number }[];
  expect(clips.length).toBeGreaterThanOrEqual(3);

  // Two drafts pass the rules; a third is made after a stricter maximum
  // length, so it needs a fix.
  const drafts: Draft[] = [];
  for (const clip of clips.slice(0, 2)) {
    const made = await request.post("/api/drafts", {
      data: { clip_id: clip.id },
    });
    drafts.push((await made.json()) as Draft);
  }
  await request.patch(`/api/campaigns/${campaignId}`, {
    data: { max_duration_s: 1 },
  });
  const fix = await request.post("/api/drafts", {
    data: { clip_id: clips[2].id },
  });
  expect(((await fix.json()) as Draft).status).toBe("needs_fix");
  expect(drafts.map((d) => d.status)).toEqual(["pending", "pending"]);

  // Test mode has no social account to post to, so the approval itself is
  // answered by a stand-in that behaves like the API (and the approved
  // draft then leaves the real list).
  const approved = new Set<number>();
  await page.route("**/api/drafts/*/approve", (route) => {
    const id = Number(new URL(route.request().url()).pathname.split("/")[3]);
    approved.add(id);
    const draft = drafts.find((d) => d.id === id)!;
    return route.fulfill({
      json: {
        draft: { ...draft, status: "approved" },
        posts: [
          {
            id: 1,
            clip_id: draft.clip_id,
            account_id: 1,
            platform: "youtube",
            payload: {},
            thumbnail_asset_id: null,
            scheduled_at: "2030-01-14T08:00:00Z",
            status: "queued",
            external_post_id: null,
            url: null,
            error: null,
            attempts: 0,
            attempted_at: null,
            next_attempt_at: null,
          },
        ],
      },
    });
  });
  await page.route("**/api/drafts?status=pending*", async (route) => {
    const response = await route.fetch();
    const list = (await response.json()) as Draft[];
    return route.fulfill({
      response,
      json: list.filter((d) => !approved.has(d.id)),
    });
  });

  await page.getByRole("link", { name: "Approval inbox" }).click();
  await expect(page.getByRole("tab", { name: "To approve (2)" })).toBeVisible();
  const cards = page.getByRole("article");
  await expect(cards).toHaveCount(2);
  const first = cards.first();
  await expect(first).toHaveAttribute("aria-current", "true");
  await expect(first.getByText("Spring clips")).toBeVisible();
  await expect(first.getByText("$1.50 per 1,000 views")).toBeVisible();
  await expect(first.getByText(/campaign rules pass/)).toBeVisible();
  await expect
    .poll(() =>
      first
        .locator("video")
        .evaluate((video: HTMLVideoElement) => video.readyState),
    )
    .toBeGreaterThan(1);
  await page.screenshot({ path: screenshot(1), fullPage: true });

  // R opens the reason chips on the selected draft.
  await page.keyboard.press("r");
  const reasons = first.getByRole("group", { name: /^Why reject/ });
  await reasons.getByRole("button", { name: "Too long" }).click();
  await page.screenshot({ path: screenshot(2), fullPage: true });
  await page.keyboard.press("r");
  await expect(
    page.getByText("Rejected. The autopilot learns from it."),
  ).toBeVisible();
  await expect(cards).toHaveCount(1);
  const rejected = (await (
    await request.get("/api/drafts?status=rejected")
  ).json()) as (Draft & { reject_reason: string })[];
  expect(rejected.map((d) => d.reject_reason)).toEqual(["too_long"]);

  // A approves the next one into the next free slot.
  await page.keyboard.press("a");
  await expect(page.getByText(/Approved: 1 post scheduled for/)).toBeVisible();
  await expect(page.getByText("Nothing to approve")).toBeVisible();

  // The draft that fails a rule waits in Needs fix with the rule to fix.
  await page.getByRole("tab", { name: "Needs fix (1)" }).click();
  const broken = page.getByRole("article");
  await expect(broken.getByText(/1 of \d+ campaign rules fail/)).toBeVisible();
  await expect(broken.getByLabel("Maximum length: fail").first()).toBeVisible();
  await expect
    .poll(() =>
      broken
        .locator("video")
        .evaluate((video: HTMLVideoElement) => video.readyState),
    )
    .toBeGreaterThan(1);
  await page.screenshot({ path: screenshot(3), fullPage: true });

  // E opens the editor, whose back arrow returns to the inbox.
  await page.keyboard.press("e");
  await expect(page).toHaveURL(new RegExp(`/clips/${clips[2].id}$`));
  await page.getByRole("link", { name: "Back to the approval inbox" }).click();
  await expect(page).toHaveURL(/\/inbox$/);
  expect(errors).toEqual([]);
});
