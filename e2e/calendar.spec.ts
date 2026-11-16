import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

// The test server has no connected accounts and no posts, so the calendar's
// API is answered here. The clock is fixed to Mon Nov 2 2026, 10:00 local.
const NOW = new Date(2026, 10, 2, 10, 0);

const ACCOUNTS = [
  account(1, "youtube", "Late Night Clips"),
  account(2, "tiktok", "pizza.tok"),
  account(3, "instagram", "clipforge.daily"),
];

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

function localIso(day: number, hour: number, minute = 0, month = 11): string {
  return new Date(2026, month - 1, day, hour, minute).toISOString();
}

let nextId = 1;

/** A post on a day of Nov 2026 (scheduled unless a status is given). */
function post(
  day: number,
  hour: number,
  title: string,
  accountId = 1,
  status = "queued",
) {
  const platform = ACCOUNTS[accountId - 1].platform;
  const at = localIso(day, hour, hour % 2 ? 30 : 0);
  const done = status === "published" || status === "failed";
  return {
    id: nextId++,
    clip_id: 1,
    account_id: accountId,
    platform,
    payload:
      platform === "youtube"
        ? { title, description: "From the late show." }
        : { caption: `${title}\n\n#standup` },
    thumbnail_asset_id: null,
    scheduled_at: done ? null : at,
    status,
    external_post_id: null,
    url: status === "published" ? "https://youtu.be/abc" : null,
    error: status === "failed" ? "The upload timed out." : null,
    attempts: done ? 1 : 0,
    attempted_at: done ? at : null,
    next_attempt_at: null,
  };
}

const POSTS = [
  post(1, 18, "Why pizza is a meal plan", 1, "published"),
  post(2, 9, "The taxi driver who knew everything", 2, "published"),
  post(2, 17, "My mom on video calls", 3, "failed"),
  post(3, 9, "Airport security, again"),
  post(3, 11, "The gym membership saga", 2),
  post(3, 13, "Dating apps explained", 3),
  post(3, 15, "Landlord texts", 1),
  post(3, 19, "Group chat chaos", 2),
  post(5, 12, "Self checkout rage", 1, "draft"),
  post(9, 8, "Cooking with a smoke alarm", 3),
  post(12, 18, "The wedding toast", 1),
  post(17, 10, "Plants I have killed", 2),
  post(24, 20, "Thanksgiving seating chart", 1),
];

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-149-${index}.png`, import.meta.url),
  );
}

/** Save the page (transitions finished, so a theme switch is fully drawn). */
async function shoot(page: Page, index: number): Promise<void> {
  await page.screenshot({ path: screenshot(index), animations: "disabled" });
}

/** Answer the calendar's API calls; returns the PATCH bodies sent. */
async function mockCalendarApi(page: Page): Promise<unknown[]> {
  const patches: unknown[] = [];
  await page.route("**/api/accounts", (route) =>
    route.fulfill({ json: ACCOUNTS }),
  );
  await page.route("**/api/posts?*", (route) => route.fulfill({ json: POSTS }));
  await page.route("**/api/posts", (route) => route.fulfill({ json: POSTS }));
  await page.route("**/api/posts/*", (route) => {
    const body = route.request().postDataJSON();
    patches.push(body);
    const id = Number(route.request().url().split("/").pop());
    return route.fulfill({
      json: { ...POSTS.find((each) => each.id === id), ...body },
    });
  });
  await page.route("**/api/projects", (route) =>
    route.fulfill({
      json: [
        {
          id: 1,
          title: "Late show, Nov 1",
          source_url: "",
          source_path: "late-show.mp4",
          status: "done",
          result_set: 1,
        },
      ],
    }),
  );
  await page.route("**/api/projects/1/clips", (route) =>
    route.fulfill({
      json: POSTS.slice(0, 5).map((each, index) => ({
        id: index + 1,
        title: String(each.payload.title ?? each.payload.caption).split(
          "\n",
        )[0],
        start: 0,
        end: 30 + index * 7,
        cut_ranges: [],
      })),
    }),
  );
  await page.route("**/api/clips/1", (route) =>
    route.fulfill({
      json: {
        id: 1,
        project_id: 1,
        title: "The wedding toast",
        description: "From the late show.",
        hashtags: ["standup", "wedding"],
      },
    }),
  );
  return patches;
}

test("the calendar shows posts by day, moves a scheduled one and opens the bulk scheduler", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.clock.setFixedTime(NOW);
  await page.setViewportSize({ width: 1440, height: 1000 });
  const patches = await mockCalendarApi(page);

  await page.goto("/calendar");
  await expect(
    page.getByRole("heading", { name: "November 2026" }),
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Post navigation" }),
  ).toBeVisible();
  const nov3 = page.getByRole("gridcell", { name: "Nov 3", exact: true });
  await expect(nov3.getByText("Airport security, again")).toBeVisible();
  await expect(nov3.getByRole("button", { name: "See 2 more" })).toBeVisible();
  await expect(
    page.getByRole("gridcell", { name: "Nov 2, today" }),
  ).toBeVisible();
  await shoot(page, 1);

  await nov3.getByRole("button", { name: "See 2 more" }).click();
  await expect(nov3.getByText("Group chat chaos")).toBeVisible();
  await shoot(page, 2);
  await nov3.getByRole("button", { name: "See less" }).click();

  await page
    .getByRole("button", { name: /Cooking with a smoke alarm/ })
    .dragTo(page.getByRole("gridcell", { name: "Nov 10", exact: true }));
  await expect.poll(() => patches).toEqual([{ scheduled_at: localIso(10, 8) }]);
  await expect(page.getByText(/^Moved to Nov 10, /)).toBeVisible();

  await page.getByRole("button", { name: /The wedding toast/ }).click();
  const sheet = page.getByRole("dialog", { name: "The wedding toast" });
  await expect(sheet.getByLabel("Publish at", { exact: true })).toHaveValue(
    "2026-11-12T18:00",
  );
  await expect(sheet.getByRole("link", { name: "Open clip" })).toBeVisible();
  await expect(sheet.getByLabel("Title", { exact: true })).toHaveValue(
    "The wedding toast",
  );
  await shoot(page, 3);
  await sheet.getByRole("button", { name: "Close" }).click();

  await page.getByRole("button", { name: "Bulk schedule" }).click();
  const bulk = page.getByRole("dialog", { name: "Bulk schedule" });
  await bulk.getByLabel(/Late Night Clips/).check();
  await bulk.getByLabel(/pizza\.tok/).check();
  await bulk.getByLabel("Select all", { exact: true }).check();
  await expect(
    bulk.getByRole("button", { name: "Schedule 10 posts" }),
  ).toBeDisabled();
  await expect(bulk.getByRole("tab", { name: "TikTok" })).toBeVisible();
  await expect(bulk.getByLabel("Times of day", { exact: true })).toHaveValue(
    "09:00, 18:00",
  );
  await shoot(page, 4);
  await bulk.getByRole("button", { name: "Close" }).click();

  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await shoot(page, 5);
  await page.getByRole("button", { name: "Switch to light theme" }).click();

  await page.getByRole("button", { name: "Week", exact: true }).click();
  await expect(page.getByRole("gridcell")).toHaveCount(7);
  await expect(page.getByText("Group chat chaos")).toBeVisible();
  await shoot(page, 6);

  expect(errors).toEqual([]);
});
