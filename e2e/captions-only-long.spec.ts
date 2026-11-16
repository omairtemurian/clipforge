import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

test.use({ viewport: { width: 1280, height: 800 } });

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(
      `../.agent/screenshots/steering-captions-only-${index}.png`,
      import.meta.url,
    ),
  );
}

test("Captions only on a 20 min video warns it makes one clip", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/sources/probe", (route) =>
    route.fulfill({
      json: {
        url: "https://youtu.be/long",
        title: "A 20 minute talk",
        duration: 1200,
        thumbnail_url: "",
      },
    }),
  );

  await page.goto("/");
  const chip = page.getByRole("button", {
    name: "Captions only (no clipping — whole video as one clip)",
  });
  await expect(chip).toBeVisible();
  await chip.click();
  await page.screenshot({ path: screenshot(1) });

  await page.getByLabel("Video link").fill("https://youtu.be/long");
  await page.getByRole("button", { name: "Get clips" }).click();
  const settings = page.getByRole("dialog", { name: "Clip settings" });
  const note = settings.getByRole("note", { name: "Long captions-only clip" });
  await expect(note).toContainText("This makes one 20:00 clip, not shorts.");
  await page.screenshot({ path: screenshot(2) });

  await note.getByRole("button", { name: "Switch to AI clipping" }).click();
  await expect(
    settings.getByRole("tab", { name: "AI clipping" }),
  ).toHaveAttribute("aria-selected", "true");
  expect(errors).toEqual([]);
});
