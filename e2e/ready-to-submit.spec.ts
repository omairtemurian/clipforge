import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-186-${index}.png`, import.meta.url),
  );
}

const POST_URL = "https://www.youtube.com/shorts/abc123";
const submission = (id: number, title: string, campaign: string) => ({
  id,
  post_id: id,
  campaign_id: id,
  submitted_at: null,
  answered_at: null,
  status: "not_submitted",
  approved_views: null,
  payout_usd: null,
  notes: "",
  platform: "youtube",
  post_url: `${POST_URL}${id}`,
  clip_id: id,
  clip_title: title,
  campaign_name: campaign,
  copy_text: `${POST_URL}${id}\n\nCampaign: ${campaign}\nPlatform: youtube`,
});

test("copy a published post and tick it as submitted on the Ready to submit list", async ({
  page,
  context,
}) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);

  // Test mode has no social account to publish with, so the tracker's list
  // is answered by a stand-in that behaves like the API.
  let waiting = [
    submission(1, "Big laugh", "Spring clips"),
    submission(2, "Chef moment", "Pizza clips"),
  ];
  await page.route("**/api/submissions?status=not_submitted", (route) =>
    route.fulfill({ json: waiting }),
  );
  await page.route("**/api/submissions/1", (route) => {
    waiting = waiting.filter((item) => item.id !== 1);
    return route.fulfill({
      json: {
        ...submission(1, "Big laugh", "Spring clips"),
        status: "submitted",
      },
    });
  });

  await page.goto("/");
  await page.getByRole("link", { name: "Ready to submit" }).click();
  await expect(page).toHaveURL(/\/submit$/);
  await expect(
    page.getByRole("heading", { name: "Ready to submit" }),
  ).toBeVisible();
  await expect(page.getByText(/2 published posts are waiting/)).toBeVisible();
  await expect(page.getByText("Pizza clips")).toBeVisible();
  await page.screenshot({ path: screenshot(1), fullPage: true });

  await page
    .getByRole("button", { name: "Copy for submission: Big laugh" })
    .click();
  await expect(page.getByText("Copied")).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain(
    `${POST_URL}1`,
  );

  await page
    .getByRole("checkbox", { name: /Submitted on the campaign board/ })
    .first()
    .click();
  await expect(page.getByText("Big laugh")).toHaveCount(0);
  await expect(page.getByText(/1 published post is waiting/)).toBeVisible();
  await page.screenshot({ path: screenshot(2), fullPage: true });

  // The daily digest time is set with the other notification settings.
  await page.goto("/settings");
  const notifications = page.getByRole("region", { name: "Notifications" });
  await expect(notifications.getByLabel("Daily digest at")).toHaveValue(
    "08:00",
  );
  await notifications.getByLabel("Daily digest at").scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(3) });
  expect(errors).toEqual([]);
});
