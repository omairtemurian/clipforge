import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);
const SRT = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.srt", import.meta.url),
);

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-69-${index}.png`, import.meta.url),
  );
}

test("the Captions only chip and attached subtitles reach the clip settings", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  await page.goto("/");
  await page.getByRole("button", { name: "Captions only" }).click();
  await page.getByLabel("Upload a subtitles file").setInputFiles(SRT);
  await expect(page.getByText("sample.srt")).toBeVisible();
  await page.screenshot({ path: screenshot(1) });

  await page.getByLabel("Upload a video file").setInputFiles(SAMPLE);
  const settings = page.getByRole("dialog", { name: "Clip settings" });
  await expect(
    settings.getByRole("tab", { name: "Captions only" }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(
    settings.getByRole("button", { name: "Remove subtitles" }),
  ).toBeVisible();
  await page.screenshot({ path: screenshot(2) });
  expect(errors).toEqual([]);
});
