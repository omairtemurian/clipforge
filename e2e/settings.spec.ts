import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-171-${index}.png`, import.meta.url),
  );
}

test("Settings shows every section and a test notification reaches the bell", async ({
  page,
}) => {
  const problems: string[] = [];
  page.on("pageerror", (error) => problems.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") problems.push(message.text());
  });

  // Earlier specs leave unread notifications (finished jobs): start from none.
  const readAll = await page.request.post("/api/notifications/read-all");
  expect(readAll.ok()).toBe(true);
  await page.goto("/settings");
  for (const name of [
    "Language model",
    "Defaults for new projects",
    "Platform connections",
    "Notifications",
    "Usage",
    "Storage paths",
    "Engines",
  ]) {
    await expect(page.getByRole("region", { name })).toBeVisible();
  }
  await expect(page.getByLabel("SMTP password")).toHaveAttribute(
    "type",
    "password",
  );

  const notifications = page.getByRole("region", { name: "Notifications" });
  await notifications.getByRole("button", { name: "Send a test" }).click();
  await expect(
    page.getByRole("button", { name: "Notifications, 1 unread" }),
  ).toBeVisible();
  await page
    .getByRole("region", { name: "Defaults for new projects" })
    .scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(1) });

  await page.getByRole("button", { name: "Notifications, 1 unread" }).click();
  await expect(page.getByText("Test notification").first()).toBeVisible();
  await page.screenshot({ path: screenshot(2) });
  expect(problems).toEqual([]);
});
