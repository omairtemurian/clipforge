import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-197-${index}.png`, import.meta.url),
  );
}

test("the Settings page shows which engine transcribes", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  await page.goto("/settings");

  const select = page.getByLabel("Transcription engine");
  await expect(select).toHaveValue("auto");
  await expect(page.getByText(/Running on:/)).toContainText(
    /Apple GPU \(MLX\)|CPU \(faster-whisper\)/,
  );
  await select.scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(1) });
  expect(errors).toEqual([]);
});
