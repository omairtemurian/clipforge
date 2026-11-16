import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-145-${index}.png`, import.meta.url),
  );
}

const ACCOUNTS = [
  {
    id: 1,
    platform: "youtube",
    external_id: "UC1",
    display_name: "Main channel",
    token_ref: "ref1",
    scopes: [],
    connected_at: "2026-10-31T10:00:00",
    restrictions: ["Unaudited project: uploads are private"],
    is_default: true,
    avatar_url: null,
    always_hashtags: [],
  },
  {
    id: 2,
    platform: "instagram",
    external_id: "17841",
    display_name: "clip_page",
    token_ref: "ref2",
    scopes: [],
    connected_at: "2026-10-31T11:00:00",
    restrictions: [],
    is_default: true,
    avatar_url: null,
    always_hashtags: [],
  },
];

test("social accounts page shows the developer app state and the connect modal", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");

  await page.getByRole("link", { name: "Social accounts" }).click();
  await expect(
    page.getByRole("heading", { name: "Social accounts", level: 1 }),
  ).toBeVisible();
  await expect(page.getByText(/No accounts connected yet/)).toBeVisible();
  const filters = page.getByRole("group", { name: "Filter by platform" });
  await expect(filters.getByRole("button", { name: "Facebook" })).toBeVisible();
  await expect(
    page.getByRole("listitem", { name: "TikTok developer app" }),
  ).toContainText("TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET");
  await page.screenshot({ path: screenshot(1) });

  await page.getByRole("button", { name: "Add account" }).click();
  const dialog = page.getByRole("dialog", {
    name: "Social account connections",
  });
  await expect(dialog.getByText("Needs developer app keys")).toHaveCount(4);
  await page.screenshot({ path: screenshot(2) });
  await dialog.getByRole("button", { name: "Close" }).first().click();
  await expect(dialog).toBeHidden();

  // Accounts need a real platform sign-in: show the list with two seeded.
  await page.route("**/api/accounts", (route) =>
    route.fulfill({ json: ACCOUNTS }),
  );
  await page.reload();
  const youtube = page.getByRole("listitem", {
    name: "Main channel (YouTube)",
  });
  await expect(youtube).toContainText("Unaudited project");
  await expect(youtube).toContainText("Connected as Main channel");
  await expect(
    youtube.getByRole("button", {
      name: "Main channel (YouTube) is the default account",
    }),
  ).toBeDisabled();
  await filters.getByRole("button", { name: "Instagram" }).click();
  await expect(youtube).toHaveCount(0);
  await expect(
    page.getByRole("listitem", { name: "clip_page (Instagram)" }),
  ).toBeVisible();
  await filters.getByRole("button", { name: "All" }).click();
  await page.screenshot({ path: screenshot(3) });

  expect(errors).toEqual([]);
});
