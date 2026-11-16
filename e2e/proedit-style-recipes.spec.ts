import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

/** Where screenshot index of this check is saved. */
function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-231-${index}.png`, import.meta.url),
  );
}

const RECIPE_FILE = {
  format: "clipforge.style_recipe",
  version: 1,
  name: "Night phonk",
  description: "Fast cuts on the beat, dark and contrasty.",
  reference_count: 2,
  targets: {
    metrics: {
      cuts_per_minute: { median: 36, low: 30, high: 42, count: 2 },
      mean_luma: { median: 0.3, low: 0.24, high: 0.36, count: 2 },
      bpm: { median: 145, low: 140, high: 150, count: 2 },
    },
    caption_color: "#ffd000",
  },
};

test("import a style recipe, edit its targets and export it", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.goto("/proedit/style-recipes");
  await expect(
    page.getByRole("heading", { name: "Style recipes" }),
  ).toBeVisible();

  await page.getByLabel("Recipe file").setInputFiles({
    name: "night-phonk.style-recipe.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(RECIPE_FILE)),
  });
  const editor = page.getByRole("region", { name: "Recipe Night phonk" });
  const cuts = editor.getByRole("slider", { name: "Cuts", exact: true });
  await expect(cuts).toHaveValue("36");
  await page.screenshot({ path: screenshot(1), animations: "disabled" });

  await cuts.fill("60");
  await editor.getByLabel("Description").fill("Faster cuts.");
  await editor.getByRole("button", { name: "Save recipe" }).click();
  await expect(editor.getByText("Range 54/min to 66/min")).toBeVisible();
  await expect(
    editor.getByRole("button", { name: "Save recipe" }),
  ).toBeDisabled();
  await page.screenshot({
    path: screenshot(2),
    fullPage: true,
    animations: "disabled",
  });

  const download = page.waitForEvent("download");
  await editor.getByRole("link", { name: "Export JSON" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("night-phonk.style-recipe.json");
  const exported = JSON.parse(await readFile(await file.path(), "utf8"));
  expect(exported.description).toBe("Faster cuts.");
  expect(exported.targets.metrics.cuts_per_minute).toEqual({
    median: 60,
    low: 54,
    high: 66,
    count: 2,
  });
  expect(Object.keys(exported).sort()).toEqual([
    "description",
    "format",
    "name",
    "reference_count",
    "targets",
    "version",
  ]);
  expect(errors).toEqual([]);
});
