import { expect, test, type APIRequestContext } from "@playwright/test";
import { fileURLToPath } from "node:url";

// The campaign end to end (SPEC-v2 3.18): the owner types a campaign in,
// the creator's fresh upload becomes a project with the campaign preset,
// its clips pass the rule check, one is scheduled, the platform publishes
// it, the owner submits it on the campaign board, enters the board's answer
// and payout, and the campaign's earnings add up. Test mode cannot reach
// YouTube or a platform, so the test server's stand-ins
// (api/testmode_routes.py) connect an account, hand Auto Import the upload
// with the fixture video as its source and publish the queued post.

const CHANNEL = "UCclipforgeE2eCampaign00";
const PIPELINE_TIMEOUT = 180_000;
const RATE = 2.5;
const APPROVED_VIEWS = 12_345;
// 12,345 / 1,000 x $2.50 = $30.8625.
const EXPECTED_ESTIMATE = "$30.86";
const PAYOUT = "30";
// A 1x1 PNG: the API only checks the image's magic bytes.
const PROOF = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-192-${index}.png`, import.meta.url),
  );
}

interface Post {
  id: number;
  clip_id: number;
  account_id: number;
  status: string;
  url: string | null;
}

let projectId: number | undefined;
let accountId: number | undefined;

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

/** Tomorrow at 09:00 local time, as a datetime-local value. */
function tomorrowAtNine(): string {
  const day = new Date();
  day.setDate(day.getDate() + 1);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}T09:00`;
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
  if (projectId !== undefined) {
    await waitUntilEnded(request, projectId);
    await request.delete(`/api/projects/${projectId}`);
  }
  if (accountId !== undefined)
    await request.delete(`/api/accounts/${accountId}`);
  projectId = accountId = undefined;
});

test("campaign: create, fresh upload, preset clips, rules, schedule, submit, payout, earnings", async ({
  page,
  request,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 120_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  // The test server's LLM answers every prompt with the curate reply, so
  // the AI post copy is answered here.
  await page.route("**/api/clips/*/post-copy", (route) =>
    route.fulfill({
      json: {
        title: "Afro's best moment",
        caption: "Clip from Afro",
        hashtags: ["clipforge", "summer"],
      },
    }),
  );

  const account = await request.post("/api/testmode/accounts/youtube", {
    params: { name: "Summer Clips Channel" },
  });
  expect(account.status()).toBe(201);
  accountId = ((await account.json()) as { id: number }).id;

  // 1. The owner creates the campaign with its rules, rate, the creator's
  // channel and the permission evidence.
  await page.goto("/");
  await page.getByRole("link", { name: "Campaigns" }).click();
  const form = page.getByRole("form", { name: "New campaign" });
  await form.getByLabel("Name").fill("Summer clips");
  await form.getByLabel("Creator", { exact: true }).fill("Afro");
  await form.getByLabel("Rate per 1,000 views (USD)").fill(String(RATE));
  await form
    .getByLabel("Creator channel links")
    .fill(`https://www.youtube.com/channel/${CHANNEL}`);
  await form.getByRole("checkbox", { name: "YouTube" }).check();
  await form.getByLabel("Required hashtags").fill("#clipforge #summer");
  await form.getByLabel("Required credit line").fill("Clip from Afro");
  await form
    .getByLabel("Permission source link")
    .fill("https://example.com/permission");
  await form
    .getByLabel("Permission screenshot")
    .setInputFiles({ name: "proof.png", mimeType: "image/png", buffer: PROOF });
  await form.getByRole("button", { name: "Create campaign" }).click();
  const saved = page.getByRole("form", { name: "Edit Summer clips" });
  await expect(saved.getByText(/Complete, saved .* is allowed/)).toBeVisible();
  await page.screenshot({ path: screenshot(1), fullPage: true });
  const campaign = (
    (await (await request.get("/api/campaigns")).json()) as {
      id: number;
      name: string;
    }[]
  ).find((c) => c.name === "Summer clips")!;

  // 2. The creator uploads: Auto Import makes a fresh-upload project with
  // the campaign's preset.
  const imported = await request.post(
    `/api/testmode/channels/${CHANNEL}/uploads`,
    { params: { video_id: "summerclip1", title: "Summer special" } },
  );
  expect(imported.status()).toBe(201);
  projectId = ((await imported.json()) as { project_id: number }).project_id;
  const project = await (
    await request.get(`/api/projects/${projectId}`)
  ).json();
  expect(project).toMatchObject({
    campaign_id: campaign.id,
    source_rights: "permission",
    fresh_upload: true,
  });
  await waitUntilEnded(request, projectId);

  // 3. Its clips carry the campaign preset and pass the rule check.
  await page.goto(`/projects/${projectId}`);
  await expect(
    page.getByRole("heading", { name: /^Clips \(\d+\)$/ }),
  ).toBeVisible({ timeout: PIPELINE_TIMEOUT });
  await expect(page.getByLabel("Campaign", { exact: true })).toHaveValue(
    String(campaign.id),
  );
  const card = page.getByRole("article").first();
  await expect(card).toContainText("Clip from Afro");
  await page.screenshot({ path: screenshot(2), fullPage: true });

  await card.getByRole("link", { name: "Edit clip" }).click();
  await page.getByRole("button", { name: "Rules" }).click();
  const panel = page.getByRole("complementary", { name: "Rules panel" });
  await expect(
    panel.getByRole("listitem", { name: "Required hashtags: pass" }),
  ).toBeVisible();
  await expect(
    panel.getByRole("listitem", { name: "Credit line: pass" }),
  ).toBeVisible();
  await expect(panel.getByRole("status")).toContainText(
    "All rules pass. This clip can be published.",
  );
  await page.screenshot({ path: screenshot(3) });

  // 4. The owner schedules the clip on the campaign's platform.
  await page.goto(`/projects/${projectId}`);
  await page
    .getByRole("article")
    .first()
    .getByRole("button", { name: "More posting options" })
    .click();
  await page.getByRole("button", { name: "Schedule…" }).click();
  const modal = page.getByRole("dialog", { name: "Schedule post" });
  await modal.getByLabel(/Summer Clips Channel/).check();
  await expect(modal.getByLabel("Title")).toHaveValue("Afro's best moment");
  await modal.getByRole("button", { name: "Pick time" }).click();
  await modal.getByLabel("Publish at").fill(tomorrowAtNine());
  await modal.getByRole("button", { name: "Schedule", exact: true }).click();
  await expect(page.getByText(/^Scheduled 1 post/)).toBeVisible();
  await expect(modal).toBeHidden();
  const queued = (
    (await (await request.get("/api/posts")).json()) as Post[]
  ).filter((p) => p.status === "queued");
  expect(queued.map((p) => p.account_id)).toEqual([accountId]);

  // 5. Its time comes and the platform publishes it.
  const published = await request.post(
    `/api/testmode/posts/${queued[0].id}/publish`,
  );
  expect(published.status()).toBe(200);
  const post = (await published.json()) as Post;
  expect(post.status).toBe("published");

  // 6. The owner submits it on the campaign board, then enters the board's
  // answer, the approved views and the payout.
  await page.getByRole("link", { name: "Campaigns" }).click();
  await page.getByRole("button", { name: /Summer clips/ }).click();
  const tracker = page.getByRole("region", { name: "Submissions" });
  await expect(tracker.getByText(post.url!)).toBeVisible();
  await expect(
    tracker.getByText("Not submitted", { exact: true }),
  ).toBeVisible();
  await tracker
    .getByRole("checkbox", { name: /Submitted on the campaign board/ })
    .click();
  const details = tracker.getByRole("form", { name: /^Details of / });
  await expect(details).toBeVisible();
  await details.getByLabel("Answer of the board").selectOption("approved");
  await details.getByLabel("Approved views").fill(String(APPROVED_VIEWS));
  await details.getByLabel("Payout (USD)").fill(PAYOUT);
  await details.getByRole("button", { name: "Save details" }).click();
  await expect(
    tracker.locator('[data-slot="pill"]', { hasText: "Approved" }),
  ).toBeVisible();

  // 7. The campaign's earnings show the exact numbers.
  const earnings = tracker.getByRole("region", { name: "Earnings" });
  const figure = (label: string) =>
    earnings.locator("div", { has: page.getByText(label, { exact: true }) });
  await expect(figure("Approved views").locator("dd")).toHaveText("12,345");
  await expect(figure("Estimated earnings").locator("dd")).toHaveText(
    EXPECTED_ESTIMATE,
  );
  await expect(figure("Payouts").locator("dd")).toHaveText("$30.00");
  await expect(earnings).toContainText(
    "Estimate: approved views / 1,000 × $2.50",
  );
  await tracker.scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(4), fullPage: true });

  const [submission] = (await (
    await request.get(`/api/submissions?campaign_id=${campaign.id}`)
  ).json()) as { status: string; approved_views: number; payout_usd: number }[];
  expect(submission).toMatchObject({
    status: "approved",
    approved_views: APPROVED_VIEWS,
    payout_usd: 30,
  });
  expect(errors).toEqual([]);
});
