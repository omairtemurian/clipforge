import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

const FILE_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz012345";

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-66-${index}.png`, import.meta.url),
  );
}

function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

test("without Google credentials the Drive dialog says what to set", async ({
  page,
}) => {
  const errors = watchErrors(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Google Drive" }).click();
  const dialog = page.getByRole("dialog", { name: "Import from Google Drive" });
  await expect(dialog.getByText("Google Drive needs credentials")).toBeVisible();
  await expect(dialog.getByRole("link", { name: "See setup" })).toBeVisible();
  await page.screenshot({ path: screenshot(1) });

  const answer = await page.request.post("/api/sources/gdrive/import", {
    data: { file: FILE_ID },
  });
  expect(answer.status()).toBe(412);
  expect(errors).toEqual([]);
});

test("a connected Drive link opens the clip settings for that video", async ({
  page,
}) => {
  // Google is not reachable from tests: the connected API answers are faked.
  const errors = watchErrors(page);
  await page.route("**/api/sources/gdrive", (route) =>
    route.fulfill({ json: { configured: true, connected: true } }),
  );
  await page.route("**/api/sources/gdrive/file", (route) =>
    route.fulfill({
      json: {
        id: FILE_ID,
        name: "Team offsite talk.mp4",
        mime_type: "video/mp4",
        size: 4096,
        duration: 754,
      },
    }),
  );
  await page.goto("/");

  await page.getByRole("button", { name: "Google Drive" }).click();
  const dialog = page.getByRole("dialog", { name: "Import from Google Drive" });
  await dialog
    .getByLabel("Drive link")
    .fill(`https://drive.google.com/file/d/${FILE_ID}/view`);
  await page.screenshot({ path: screenshot(2) });
  await dialog.getByRole("button", { name: "Continue" }).click();

  const panel = page.getByRole("dialog", { name: "Clip settings" });
  await expect(panel.getByText("Team offsite talk")).toBeVisible();
  await page.screenshot({ path: screenshot(3) });
  expect(errors).toEqual([]);
});
