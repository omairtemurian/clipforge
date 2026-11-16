import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

// The test server has no connected accounts and no posts, so the history's
// API is answered here (newest first, as GET /posts/history answers).
const ACCOUNTS = [
  account(1, "youtube", "Late Night Clips"),
  account(2, "tiktok", "pizza.tok"),
  account(3, "instagram", "clipforge.daily"),
];

const SKIPPED =
  "Skipped: it was due while ClipForge was off (Settings > Posting). " +
  "Post it now from its details if you still want it out.";

function account(id: number, platform: string, name: string) {
  return {
    id,
    platform,
    external_id: `ext${id}`,
    display_name: name,
    token_ref: `ref${id}`,
    scopes: [],
    connected_at: "2026-10-01T10:00:00Z",
    restrictions: [],
    is_default: false,
    avatar_url: null,
    always_hashtags: [],
  };
}

function localIso(day: number, hour: number): string {
  return new Date(2026, 10, day, hour, 0).toISOString();
}

function post(
  id: number,
  accountId: number,
  status: string,
  day: number,
  hour: number,
  title: string,
) {
  const platform = ACCOUNTS[accountId - 1].platform;
  const tried = status !== "skipped";
  return {
    id,
    clip_id: 1,
    account_id: accountId,
    platform,
    payload:
      platform === "youtube" ? { title } : { caption: `${title}\n\n#standup` },
    thumbnail_asset_id: null,
    scheduled_at: localIso(day, hour),
    status,
    external_post_id: status === "published" ? `x${id}` : null,
    url:
      status === "published"
        ? platform === "youtube"
          ? `https://youtu.be/clip${id}`
          : `https://www.tiktok.com/@pizza.tok/video/${id}`
        : null,
    error:
      status === "failed"
        ? "The upload timed out (gave up after 5 attempts)"
        : status === "skipped"
          ? SKIPPED
          : null,
    attempts: tried ? 1 : 0,
    attempted_at: tried ? localIso(day, hour) : null,
    next_attempt_at: null,
  };
}

const HISTORY = [
  post(6, 2, "published", 2, 9, "The taxi driver who knew everything"),
  post(5, 1, "skipped", 1, 21, "Airport security, again"),
  post(4, 3, "skipped", 1, 18, "Landlord texts"),
  post(3, 3, "failed", 1, 12, "My mom on video calls"),
  post(2, 1, "published", 31, 18, "Why pizza is a meal plan"),
  post(1, 2, "published", 30, 9, "Group chat chaos"),
];

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-151-${index}.png`, import.meta.url),
  );
}

async function shoot(page: Page, index: number): Promise<void> {
  await page.screenshot({ path: screenshot(index), animations: "disabled" });
}

/** Answer the history's API calls; returns the posts published again. */
async function mockHistoryApi(page: Page): Promise<string[]> {
  const published: string[] = [];
  await page.route("**/api/accounts", (route) =>
    route.fulfill({ json: ACCOUNTS }),
  );
  await page.route("**/api/posts/history?*", (route) => {
    const status = new URL(route.request().url()).searchParams.get("status");
    return route.fulfill({
      json: HISTORY.filter((each) => !status || each.status === status),
    });
  });
  await page.route("**/api/posts/*/publish", (route) => {
    published.push(route.request().url());
    const id = Number(route.request().url().split("/").at(-2));
    const found = HISTORY.find((each) => each.id === id);
    return route.fulfill({ json: { ...found, status: "queued", error: null } });
  });
  await page.route("**/api/clips/1", (route) =>
    route.fulfill({
      json: { id: 1, project_id: 1, title: "Late show", hashtags: [] },
    }),
  );
  return published;
}

test("the post history lists what went out with links and posts a skipped post now", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  const published = await mockHistoryApi(page);

  await page.goto("/");
  await page
    .getByRole("navigation", { name: "Post navigation" })
    .getByRole("link", { name: "Post history" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Post history" }),
  ).toBeVisible();
  const rows = page.getByRole("list", { name: "Posts" }).getByRole("listitem");
  await expect(rows).toHaveCount(6);
  await expect(
    rows.first().getByRole("link", { name: "View post" }),
  ).toHaveAttribute("href", "https://www.tiktok.com/@pizza.tok/video/6");
  await expect(rows.nth(1).getByText("Skipped", { exact: true })).toBeVisible();
  await shoot(page, 1);

  await page.getByLabel("Status").selectOption("skipped");
  await expect(rows).toHaveCount(2);
  await page.getByRole("button", { name: "Airport security, again" }).click();
  const sheet = page.getByRole("dialog", { name: "Airport security, again" });
  await expect(sheet.getByRole("alert")).toHaveText(SKIPPED);
  await shoot(page, 2);
  await sheet.getByRole("button", { name: "Post now" }).click();
  await expect(page.getByText("Posting now.")).toBeVisible();
  expect(published).toEqual([
    expect.stringMatching(/\/api\/posts\/5\/publish$/),
  ]);

  await page.goto("/settings");
  const policy = page.getByLabel("Posts missed while ClipForge was off");
  await expect(policy).toHaveValue("post_late");
  await policy.selectOption("skip");
  await policy.scrollIntoViewIfNeeded();
  await shoot(page, 3);
  expect(errors).toEqual([]);
});
