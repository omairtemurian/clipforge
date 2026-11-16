import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-177-${index}.png`, import.meta.url),
  );
}

interface Submission {
  id: number;
  post_id: number;
  campaign_id: number;
  submitted_at: string | null;
  status: string;
  approved_views: number | null;
  payout_usd: number | null;
  notes: string;
  platform: string;
  post_url: string;
  clip_id: number;
  clip_title: string;
  campaign_name: string;
  copy_text: string;
}

test.afterEach(async ({ request }) => {
  const campaigns = await (await request.get("/api/campaigns")).json();
  for (const { id } of campaigns as { id: number }[]) {
    await request.delete(`/api/campaigns/${id}`);
  }
});

test("copy a published post for submission and track the board's answer", async ({
  page,
  request,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
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
      required_hashtags: ["spring"],
      required_credit_line: "Clip from Afro",
    },
  });
  const campaignId = ((await created.json()) as { id: number }).id;

  // Publishing to a real platform is not possible here, so the tracker's
  // reads and writes are served by a stand-in that behaves like the API.
  let current: Submission = {
    id: 1,
    post_id: 1,
    campaign_id: campaignId,
    submitted_at: null,
    status: "not_submitted",
    approved_views: null,
    payout_usd: null,
    notes: "",
    platform: "youtube",
    post_url: "https://youtu.be/abc123",
    clip_id: 1,
    clip_title: "The big moment",
    campaign_name: "Spring clips",
    copy_text:
      "https://youtu.be/abc123\n\nCampaign: Spring clips\nPlatform: YouTube\nCredit line: Clip from Afro\nHashtags: #spring",
  };
  await page.route("**/api/submissions?*", (route) =>
    route.fulfill({ json: [current] }),
  );
  await page.route("**/api/submissions/1", (route) => {
    const patch = route.request().postDataJSON() as Partial<Submission>;
    current = {
      ...current,
      ...patch,
      submitted_at: current.submitted_at ?? new Date().toISOString(),
    };
    return route.fulfill({ json: current });
  });

  await page.goto("/campaigns");
  await page.getByRole("button", { name: /Spring clips/ }).click();
  const tracker = page.getByRole("region", { name: "Submissions" });
  await expect(tracker.getByText("The big moment")).toBeVisible();
  await expect(
    tracker.getByText("Not submitted", { exact: true }),
  ).toBeVisible();

  await tracker
    .getByRole("button", { name: "Copy for submission: The big moment" })
    .click();
  await expect(tracker.getByText("Copied")).toBeVisible();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toContain("https://youtu.be/abc123");
  expect(copied).toContain("Hashtags: #spring");

  await tracker
    .getByRole("checkbox", { name: /Submitted on the campaign board/ })
    .click();
  const details = tracker.getByRole("form", {
    name: "Details of The big moment",
  });
  await expect(details).toBeVisible();
  await details.getByLabel("Answer of the board").selectOption("approved");
  await details.getByLabel("Approved views").fill("4200");
  await details.getByLabel("Payout (USD)").fill("2.1");
  await details.getByRole("button", { name: "Save details" }).click();
  await expect(
    tracker.locator('[data-slot="pill"]', { hasText: "Approved" }),
  ).toBeVisible();

  await tracker.scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(1), fullPage: true });
  expect(errors).toEqual([]);
});
