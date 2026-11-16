import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);
const PIPELINE_TIMEOUT = 180_000;

// Accounts need a real platform sign-in: the modal gets two seeded ones,
// and the post calls that would need them are answered here.
const ACCOUNTS = [
  {
    id: 1,
    platform: "youtube",
    external_id: "UC1",
    display_name: "Main channel",
    token_ref: "ref1",
    scopes: [],
    connected_at: "2026-11-01T10:00:00",
    restrictions: [],
    is_default: true,
    avatar_url: null,
    always_hashtags: [],
  },
  {
    id: 2,
    platform: "tiktok",
    external_id: "tt1",
    display_name: "pizza.tok",
    token_ref: "ref2",
    scopes: [],
    connected_at: "2026-11-01T10:00:00",
    restrictions: [],
    is_default: true,
    avatar_url: null,
    always_hashtags: [],
  },
];

let projectId: string | undefined;

function screenshot(index: number, task: number | string = 147): string {
  return fileURLToPath(
    new URL(
      `../.agent/screenshots/${typeof task === "number" ? `TASK-${task}` : task}-${index}.png`,
      import.meta.url,
    ),
  );
}

// The test server's LLM answers every prompt with the curate reply, so the
// AI post copy is answered here.
async function mockPostCopy(page: Page): Promise<string[]> {
  const options: string[] = [];
  await page.route("**/api/clips/*/post-copy", (route) => {
    const body = route.request().postDataJSON();
    options.push(body.tone ?? body.format ?? body.hashtags ?? "new");
    const youtube = body.platform === "youtube";
    return route.fulfill({
      json: {
        title: youtube ? (body.tone ? "Funny AI title" : "AI title") : "",
        caption: body.tone ? "A funnier caption." : "A caption by the AI.",
        hashtags: ["pizza", "funny"],
      },
    });
  });
  return options;
}

test.afterEach(async ({ request }) => {
  if (projectId === undefined) return;
  expect((await request.delete(`/api/projects/${projectId}`)).status()).toBe(
    204,
  );
  projectId = undefined;
});

/** Upload the fixture from Home with the source rights "own" and wait for its clips. */
async function getClips(page: Page): Promise<void> {
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
}

/** Open the "Schedule post" modal of the first clip from its Post menu. */
async function openSchedule(page: Page): Promise<void> {
  const card = page.getByRole("article").first();
  await card.getByRole("button", { name: "More posting options" }).click();
  await page.getByRole("button", { name: "Schedule…" }).click();
}

test("schedule a clip's posts from the Schedule post modal", async ({
  page,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 60_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/accounts", (route) =>
    route.fulfill({ json: ACCOUNTS }),
  );
  await mockPostCopy(page);
  let created: { targets: { account_id: number }[] } | undefined;
  const queued: string[] = [];
  const draft = (id: number) => ({
    id,
    clip_id: 1,
    account_id: id,
    platform: ACCOUNTS[id - 1].platform,
    payload: {},
    thumbnail_asset_id: null,
    scheduled_at: "2030-01-15T08:00:00Z",
    status: "draft",
    external_post_id: null,
    url: null,
    error: null,
    attempts: 0,
  });
  await page.route("**/api/clips/*/posts", (route) => {
    created = route.request().postDataJSON();
    return route.fulfill({ status: 201, json: [draft(1), draft(2)] });
  });
  await page.route("**/api/posts/*/queue", (route) => {
    queued.push(route.request().url());
    const id = Number(route.request().url().split("/").at(-2));
    return route.fulfill({ json: { ...draft(id), status: "queued" } });
  });

  await getClips(page);
  await openSchedule(page);
  const modal = page.getByRole("dialog", { name: "Schedule post" });
  await modal.getByLabel(/Main channel/).check();
  await modal.getByLabel(/pizza\.tok/).check();
  await expect(modal.getByLabel("Title")).not.toHaveValue("");
  await expect(modal.getByRole("status")).toContainText("TikTok");
  await page.screenshot({ path: screenshot(1) });

  await modal.getByRole("tab", { name: "TikTok" }).click();
  await modal.getByLabel("Who can see it").selectOption("SELF_ONLY");
  await modal.getByRole("button", { name: "Bulk schedule" }).click();
  await expect(
    modal.getByRole("button", { name: "Schedule in free slots" }),
  ).toBeEnabled();
  await page.screenshot({ path: screenshot(2) });

  await modal.getByRole("button", { name: "Pick time" }).click();
  await modal.getByLabel("Publish at").fill("2030-01-15T09:00");
  await modal.getByRole("button", { name: "Schedule", exact: true }).click();
  await expect(
    page.getByText(/^Scheduled 2 posts, the first on/),
  ).toBeVisible();
  await expect(modal).toBeHidden();
  expect(created).toMatchObject({
    targets: [
      { account_id: 1, text: { privacy: "public" } },
      { account_id: 2, text: { title: "", privacy: "SELF_ONLY" } },
    ],
  });
  expect(queued).toHaveLength(2);
  await page.screenshot({ path: screenshot(3) });
  expect(errors).toEqual([]);
});

test("the AI writes the post, rewrite changes it, a frame is the cover", async ({
  page,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 60_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/accounts", (route) =>
    route.fulfill({ json: ACCOUNTS }),
  );
  const options = await mockPostCopy(page);

  await getClips(page);
  await openSchedule(page);
  const modal = page.getByRole("dialog", { name: "Schedule post" });
  await modal.getByLabel(/Main channel/).check();
  await expect(modal.getByLabel("Title")).toHaveValue("AI title");
  await expect(modal.getByLabel("Description")).toHaveValue(
    "A caption by the AI.",
  );

  await modal.getByRole("button", { name: "Rewrite with AI" }).click();
  await page.getByRole("button", { name: "funny" }).click();
  await expect(modal.getByLabel("Title")).toHaveValue("Funny AI title");
  expect(options).toContain("funny");
  await page.screenshot({ path: screenshot(1, 148) });

  await modal.getByLabel("Cover frame").fill("1");
  await modal.getByRole("button", { name: "Use this frame" }).click();
  const chosen = modal.getByAltText("Chosen cover");
  await expect(chosen).toBeVisible();
  await expect
    .poll(() => chosen.evaluate((img: HTMLImageElement) => img.naturalWidth))
    .toBeGreaterThan(0);
  await page.screenshot({ path: screenshot(2, 148) });
  expect(errors).toEqual([]);
});

test("one click posts to the default accounts with AI text", async ({
  page,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 60_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/accounts", (route) =>
    route.fulfill({ json: ACCOUNTS }),
  );
  await mockPostCopy(page);
  let sent:
    | { platforms: string[]; texts: Record<string, { title: string }> }
    | undefined;
  await page.route("**/api/clips/*/quick-post", (route) => {
    sent = route.request().postDataJSON();
    return route.fulfill({ status: 201, json: [] });
  });

  await getClips(page);
  const card = page.getByRole("article").first();
  await card.getByRole("button", { name: "Post clip" }).click();
  const sheet = page.getByRole("dialog", { name: "Post clip" });
  await expect(sheet.getByLabel(/Main channel/)).toBeChecked();
  await expect(sheet.getByLabel("Title")).toHaveValue("AI title");
  await sheet.getByRole("tab", { name: "TikTok" }).click();
  await sheet.getByLabel("Who can see it").selectOption("SELF_ONLY");
  const postNow = sheet.getByRole("button", { name: "Post now" });
  await expect(postNow).toBeEnabled({ timeout: PIPELINE_TIMEOUT });
  await page.screenshot({ path: screenshot(1, "STEERING-quick-post") });

  await postNow.click();
  await expect(sheet).toBeHidden();
  expect(sent?.platforms).toEqual(["youtube", "tiktok"]);
  expect(sent?.texts.youtube.title).toBe("AI title");
  expect(errors).toEqual([]);
});
