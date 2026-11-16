import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const CHANNEL = "UCBR8-60-B28hp2BmDPdntcQ";

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-195-${index}.png`, import.meta.url),
  );
}

test("watch a channel and a streamer, change defaults, stop watching", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");

  await page.getByRole("link", { name: "Watchlist" }).click();
  await expect(page.getByRole("status")).toHaveText(/Polling every 60 s/);
  await expect(page.getByText("No channels yet")).toBeVisible();
  await expect(page.getByText("Needs Twitch app keys")).toBeVisible();
  await page
    .getByLabel("YouTube channel", { exact: true })
    .fill(`https://www.youtube.com/channel/${CHANNEL}`);
  await page.getByLabel("Source rights").selectOption("permission");
  await page.getByLabel("Credit line").fill("Video by YouTube");
  await page.getByRole("button", { name: "Watch channel" }).click();

  const card = page.getByRole("listitem", { name: CHANNEL });
  await expect(
    card.getByText(/Not checked yet · No new projects/),
  ).toBeVisible();
  await expect(card.getByText("Polling every 60 s")).toBeVisible();

  await page
    .getByLabel("Twitch streamer", { exact: true })
    .fill("https://www.twitch.tv/Afro");
  await page.getByRole("button", { name: "Watch streamer" }).click();
  const streamer = page.getByRole("listitem", { name: "afro" });
  await expect(streamer.getByText(/Not seen live yet/)).toBeVisible();
  // Alerts stay after their channel is removed, and earlier specs (v2
  // autopilot and campaign) leave some: none may be about this channel or
  // streamer yet.
  const recent = page.getByRole("region", { name: "Recent alerts" });
  const earlier = (await (
    await page.request.get("/api/watch/events")
  ).json()) as unknown[];
  if (earlier.length === 0) {
    await expect(recent.getByText("No alerts yet")).toBeVisible();
  } else {
    await expect(
      recent.getByRole("list", { name: "Recent alerts" }),
    ).toBeVisible();
  }
  await expect(recent).not.toContainText(CHANNEL);
  await expect(recent).not.toContainText(/afro/i);
  await page
    .getByRole("heading", { name: "Watchlist", level: 1 })
    .scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(1) });
  await recent.scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(3) });

  await card
    .getByRole("button", { name: `Edit defaults of ${CHANNEL}` })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Genre").selectOption("comedy");
  await page.screenshot({ path: screenshot(2) });
  await dialog.getByRole("button", { name: "Save defaults" }).click();
  await expect(card.getByText(/Comedy · /)).toBeVisible();

  await card.getByRole("button", { name: `Remove ${CHANNEL}` }).click();
  await card.getByRole("button", { name: `Remove ${CHANNEL}` }).click();
  await expect(page.getByText("No channels yet")).toBeVisible();
  await streamer.getByRole("button", { name: "Remove afro" }).click();
  await streamer.getByRole("button", { name: "Remove afro" }).click();
  await expect(page.getByText("No streamers yet")).toBeVisible();

  await page.goto("/auto-import");
  await expect(page).toHaveURL(/\/watchlist$/);
  expect(errors).toEqual([]);
});
