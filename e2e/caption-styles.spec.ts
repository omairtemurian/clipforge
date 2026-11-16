import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);

/** Where the screenshot number index of this check is saved. */
function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-199-${index}.png`, import.meta.url),
  );
}

test("the settings offer 30 caption templates and colors over any of them", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  await page.goto("/");
  await page.getByLabel("Upload a video file").setInputFiles(SAMPLE);
  const settings = page.getByRole("dialog", { name: "Clip settings" });
  const templates = settings.getByRole("radiogroup", {
    name: "Caption template",
  });
  await expect(templates.getByRole("radio")).toHaveCount(31, {
    timeout: 30_000,
  });
  await templates
    .getByRole("radio", { name: "Snow lime" })
    .scrollIntoViewIfNeeded();
  await expect
    .poll(
      () =>
        templates.locator("img").evaluateAll((images) => {
          const shown = images.filter((image) => {
            const box = image.getBoundingClientRect();
            return box.bottom > 100 && box.top < window.innerHeight - 80;
          });
          return shown.every(
            (image) => (image as HTMLImageElement).naturalWidth > 0,
          );
        }),
      { timeout: 90_000 },
    )
    .toBe(true);
  await page.waitForTimeout(3000);
  await page.screenshot({ path: screenshot(1) });

  await templates.getByRole("radio", { name: "Minimal" }).click();
  await settings.getByRole("button", { name: "White + green" }).click();
  await expect(settings.getByLabel("Spoken word color")).toHaveValue("#22c55e");
  await settings
    .getByRole("button", { name: "Template colors" })
    .scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(2) });

  expect(errors).toEqual([]);
});
