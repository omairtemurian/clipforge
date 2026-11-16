import { expect, test, type APIRequestContext } from "@playwright/test";
import { fileURLToPath } from "node:url";

// The autopilot end to end (SPEC-v2 3.19): a watched creator's new upload
// becomes drafts in the Approval inbox, the owner rejects one and approves
// two (queued into the autopilot's slots), and an API key may not approve
// or publish. Test mode cannot reach YouTube or a platform's sign-in, so
// the test server's stand-ins (api/testmode_routes.py) connect an account
// and hand Auto Import the new upload with the fixture video as its source.

const CHANNEL = "UCclipforgeE2eAutopilot0";
const PIPELINE_TIMEOUT = 180_000;
// A 1x1 PNG: the API only checks the image's magic bytes.
const PROOF = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-191-${index}.png`, import.meta.url),
  );
}

interface Draft {
  id: number;
  clip_id: number;
  status: string;
  reject_reason: string | null;
}

interface Post {
  id: number;
  clip_id: number;
  account_id: number;
  status: string;
  scheduled_at: string | null;
}

let projectId: number | undefined;
let accountId: number | undefined;
let keyId: number | undefined;

/** Wait until the project's processing ended. */
async function waitUntilEnded(request: APIRequestContext, id: number) {
  await expect
    .poll(
      async () =>
        (await (await request.get(`/api/projects/${id}`)).json()).status,
      { timeout: PIPELINE_TIMEOUT, intervals: [1000] },
    )
    .toMatch(/^(done|failed)$/);
}

/** The drafts of the campaign, oldest first. */
async function campaignDrafts(
  request: APIRequestContext,
  campaignId: number,
): Promise<Draft[]> {
  const drafts = (await (
    await request.get(`/api/drafts?campaign_id=${campaignId}`)
  ).json()) as Draft[];
  return drafts.sort((a, b) => a.id - b.id);
}

test.afterEach(async ({ request }) => {
  const posts = (await (await request.get("/api/posts")).json()) as Post[];
  for (const post of posts.filter((p) => p.status === "queued")) {
    await request.post(`/api/posts/${post.id}/cancel`);
  }
  const campaigns = await (await request.get("/api/campaigns")).json();
  for (const { id } of campaigns as { id: number }[]) {
    await request.delete(`/api/campaigns/${id}`);
  }
  if (keyId !== undefined) await request.delete(`/api/api-keys/${keyId}`);
  if (accountId !== undefined)
    await request.delete(`/api/accounts/${accountId}`);
  if (projectId !== undefined) {
    await waitUntilEnded(request, projectId);
    await request.delete(`/api/projects/${projectId}`);
  }
  projectId = accountId = keyId = undefined;
});

test("a new upload becomes drafts; the owner approves 2 and rejects 1, an API key gets 403", async ({
  page,
  request,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 120_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  const account = await request.post("/api/testmode/accounts/youtube", {
    params: { name: "Spring Clips Channel" },
  });
  expect(account.status()).toBe(201);
  accountId = ((await account.json()) as { id: number }).id;

  const created = await request.post("/api/campaigns", {
    data: {
      name: "Spring clips",
      creator_name: "Afro",
      allowed_platforms: ["youtube"],
      rate_per_1k_usd: 1.5,
      permission_source_url: "https://example.com/permission",
      source_channel_urls: [`https://www.youtube.com/channel/${CHANNEL}`],
    },
  });
  expect(created.status()).toBe(201);
  const campaignId = ((await created.json()) as { id: number }).id;
  await request.post(`/api/campaigns/${campaignId}/permission-screenshot`, {
    multipart: {
      file: { name: "proof.png", mimeType: "image/png", buffer: PROOF },
    },
  });
  const autopilot = await request.put(
    `/api/campaigns/${campaignId}/autopilot`,
    {
      data: {
        enabled: true,
        max_clips_per_source: 3,
        max_posts_per_day: 3,
        account_ids: [accountId],
        slots: { timezone: "Europe/Zurich", times: ["09:00", "18:00"] },
      },
    },
  );
  expect(autopilot.status()).toBe(200);

  // The creator uploads: Auto Import makes the autopilot's project, whose
  // finished process job leaves its best clips as drafts.
  const imported = await request.post(
    `/api/testmode/channels/${CHANNEL}/uploads`,
    { params: { video_id: "springclip1", title: "Spring special" } },
  );
  expect(imported.status()).toBe(201);
  projectId = ((await imported.json()) as { project_id: number }).project_id;
  await waitUntilEnded(request, projectId);
  await expect
    .poll(async () => (await campaignDrafts(request, campaignId)).length, {
      timeout: 30_000,
    })
    .toBe(3);
  const drafts = await campaignDrafts(request, campaignId);
  expect(drafts.map((d) => d.status)).toEqual([
    "pending",
    "pending",
    "pending",
  ]);

  await page.goto("/");
  await page.getByRole("link", { name: "Approval inbox" }).click();
  await expect(page.getByRole("tab", { name: "To approve (3)" })).toBeVisible();
  const cards = page.getByRole("article");
  await expect(cards).toHaveCount(3);
  const first = cards.first();
  await expect(first).toHaveAttribute("aria-current", "true");
  await expect(first.getByText("Spring clips")).toBeVisible();
  await expect(first.getByText(/campaign rules pass/)).toBeVisible();
  await expect
    .poll(() =>
      first
        .locator("video")
        .evaluate((video: HTMLVideoElement) => video.readyState),
    )
    .toBeGreaterThan(1);
  await page.screenshot({ path: screenshot(1), fullPage: true });

  // Reject the first with a reason, then approve the other two.
  await page.keyboard.press("r");
  await first
    .getByRole("group", { name: /^Why reject/ })
    .getByRole("button", { name: "Too long" })
    .click();
  await page.keyboard.press("r");
  await expect(
    page.getByText("Rejected. The autopilot learns from it."),
  ).toBeVisible();
  await expect(cards).toHaveCount(2);
  await page.keyboard.press("a");
  await expect(cards).toHaveCount(1);
  await page.keyboard.press("a");
  await expect(page.getByText("Nothing to approve")).toBeVisible();
  await expect(
    page.getByText(/Approved: 1 post scheduled for/).first(),
  ).toBeVisible();
  await page.screenshot({ path: screenshot(2), fullPage: true });

  // The inbox lists the newest draft first: that one was rejected.
  const decided = await campaignDrafts(request, campaignId);
  expect(decided.map((d) => [d.status, d.reject_reason])).toEqual([
    ["approved", null],
    ["approved", null],
    ["rejected", "too_long"],
  ]);
  const rejected = decided[2];
  const approvedClips = decided.slice(0, 2).map((d) => d.clip_id);
  const posts = ((await (await request.get("/api/posts")).json()) as Post[])
    .filter((p) => p.status === "queued")
    .sort((a, b) => a.id - b.id);
  expect(posts.map((p) => p.account_id)).toEqual([accountId, accountId]);
  const byId = (a: number, b: number) => a - b;
  expect(posts.map((p) => p.clip_id).sort(byId)).toEqual(
    approvedClips.sort(byId),
  );
  const times = posts.map((p) => Date.parse(p.scheduled_at!));
  expect(times.every((t) => t > Date.now())).toBe(true);
  expect(new Set(times).size).toBe(2);

  // Both posts wait in the calendar, in the autopilot's next free slots.
  await page.getByRole("link", { name: "Calendar" }).click();
  const firstSlot = new Date(Math.min(...times));
  if (firstSlot.getMonth() !== new Date().getMonth()) {
    await page.getByRole("button", { name: "Next month" }).click();
  }
  for (const post of posts) {
    await expect(page.locator(`[data-post-id="${post.id}"]`)).toBeVisible();
  }
  await page.screenshot({ path: screenshot(3), fullPage: true });

  // An agent's API key may read the inbox but never approve or publish.
  const key = await request.post("/api/api-keys", {
    data: { name: "Agent" },
  });
  expect(key.status()).toBe(201);
  const madeKey = (await key.json()) as { id: number; key: string };
  keyId = madeKey.id;
  const agent = { Authorization: `Bearer ${madeKey.key}` };
  const listed = await request.get("/api/v1/drafts", { headers: agent });
  expect(listed.status()).toBe(200);
  const attempts = [
    `/api/v1/drafts/${rejected.id}/approve`,
    `/api/v1/campaigns/${campaignId}/drafts/approve`,
    `/api/v1/posts/${posts[0].id}/publish`,
    `/api/v1/posts/${posts[0].id}/queue`,
    `/api/drafts/${rejected.id}/approve`,
  ];
  for (const path of attempts) {
    const answer = await request.post(path, { headers: agent, data: {} });
    expect(answer.status(), path).toBe(403);
    expect(((await answer.json()) as { error: string }).error).toBe(
      "human_only",
    );
  }
  const still = (await (
    await request.get(`/api/drafts/${rejected.id}`)
  ).json()) as Draft;
  expect(still.status).toBe("rejected");
  const after = (await (
    await request.get(`/api/posts/${posts[0].id}`)
  ).json()) as Post;
  expect(after.status).toBe("queued");
  expect(errors).toEqual([]);
});
