import { expect, test, type Locator, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);

// The pipeline (ingest, signals, curate, score, snap, reframe) runs for real
// on the 60 s fixture; only whisper and the LLM are recorded.
const PIPELINE_TIMEOUT = 180_000;
const RENDER_TIMEOUT = 120_000;

// The project the flow created; removed after the test, so the other specs
// still see a server without projects.
let projectId: string | undefined;

test.afterEach(async ({ request }) => {
  if (projectId === undefined) return;
  const response = await request.delete(`/api/projects/${projectId}`);
  expect(response.status()).toBe(204);
  projectId = undefined;
});

/**
 * Collect console errors and uncaught page errors, so the test can assert
 * that the whole flow ran without any.
 */
function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

/**
 * Upload the fixture from Home, keep the default settings in the panel that
 * opens, choose the source rights and press "Get clips"; return the gallery's cards once it lists them.
 */
async function getClips(page: Page): Promise<Locator> {
  await page.goto("/");
  await page.getByLabel("Upload a video file").setInputFiles(SAMPLE);

  const settings = page.getByRole("dialog", { name: "Clip settings" });
  await expect(settings).toBeVisible();
  await settings.getByLabel("Source rights").selectOption("own");
  await settings.getByRole("button", { name: "Get clips" }).click();

  await expect(page).toHaveURL(/\/projects\/\d+$/);
  projectId = page.url().split("/").pop();
  const heading = page.getByRole("heading", { name: /^Clips \(\d+\)$/ });
  await expect(heading).toBeVisible({ timeout: PIPELINE_TIMEOUT });
  return page.getByRole("article");
}

/** The number in the "Clip end" handle's aria-valuenow. */
async function clipEnd(page: Page): Promise<number> {
  const value = await page
    .getByRole("slider", { name: "Clip end" })
    .getAttribute("aria-valuenow");
  return Number(value);
}

/** Seconds of a "mm:ss.cc" timecode. */
function seconds(timecode: string): number {
  const [minutes, rest] = timecode.split(":");
  return Number(minutes) * 60 + Number(rest);
}

/**
 * The duration in seconds of an MP4 from its movie header ("mvhd" box:
 * version, flags, creation and modification times, timescale, duration;
 * the times are 64-bit in version 1).
 */
function mp4Duration(bytes: Buffer): number {
  const at = bytes.indexOf("mvhd", 0, "latin1");
  expect(at).toBeGreaterThan(0);
  if (bytes[at + 4] === 1) {
    return Number(bytes.readBigUInt64BE(at + 28)) / bytes.readUInt32BE(at + 24);
  }
  return bytes.readUInt32BE(at + 20) / bytes.readUInt32BE(at + 16);
}

test("upload, get clips, edit one, render it and download the mp4", async ({
  page,
}, testInfo) => {
  test.setTimeout(PIPELINE_TIMEOUT + RENDER_TIMEOUT + 60_000);
  const errors = watchErrors(page);

  const cards = await getClips(page);
  const count = await cards.count();
  expect(count).toBeGreaterThan(0);
  await expect(
    page.getByRole("heading", { name: `Clips (${count})` }),
  ).toBeVisible();
  for (const card of await cards.all()) {
    await expect(
      card.getByRole("button", { name: /^Score \d+/ }),
    ).toBeVisible();
  }

  await cards.first().getByRole("link", { name: "Edit clip" }).click();
  await expect(page).toHaveURL(/\/clips\/\d+$/);

  const words = page.getByLabel("Clip words");
  const word = words.locator("[data-word]:not([data-cut])").nth(2);
  await expect(word).toBeVisible();
  const index = await word.getAttribute("data-word");
  await word.click();
  await expect(word).toHaveAttribute("data-selected", "true");
  await page.keyboard.press("Delete");
  await expect(words.locator(`[data-word="${index}"]`)).toHaveAttribute(
    "data-cut",
    "true",
  );

  await page
    .getByRole("navigation", { name: "Editor panels" })
    .getByRole("button", { name: "Captions" })
    .click();
  const templates = page.getByRole("radiogroup", { name: "Caption template" });
  const other = templates.locator('[role="radio"][aria-checked="false"]');
  const template = other.first();
  const templateName = await template.getAttribute("aria-label");
  await template.click();
  await expect(
    templates.getByRole("radio", { name: templateName ?? "" }),
  ).toHaveAttribute("aria-checked", "true");

  const end = await clipEnd(page);
  const handle = page.getByRole("slider", { name: "Clip end" });
  await handle.focus();
  await handle.press("Shift+ArrowLeft");
  await handle.press("Shift+ArrowLeft");
  await expect.poll(() => clipEnd(page)).toBeLessThan(end - 1.5);

  const length = await page
    .getByRole("region", { name: "Clip details" })
    .getByText("Length", { exact: true })
    .locator("xpath=following-sibling::*[1]")
    .textContent();

  // The pipeline has already rendered the clip, so its Download link shows
  // the old video until this render ends: wait for the job's own toast.
  await page.getByRole("button", { name: "Render", exact: true }).click();
  await expect(
    page.getByText("The clip is rendered. Download it now."),
  ).toBeVisible({ timeout: RENDER_TIMEOUT });
  const download = page.getByRole("link", { name: "Download" });

  const [file] = await Promise.all([
    page.waitForEvent("download"),
    download.click(),
  ]);
  expect(file.suggestedFilename()).toMatch(/\.mp4$/);
  const path = testInfo.outputPath(file.suggestedFilename());
  await file.saveAs(path);
  const bytes = await readFile(path);
  expect(bytes.length).toBeGreaterThan(0);
  // An MP4 starts with its "ftyp" box: 4 size bytes, then "ftyp".
  expect(bytes.subarray(4, 8).toString("latin1")).toBe("ftyp");
  // The edited clip (word cut, end trimmed by 2 s) is what was rendered.
  expect(mp4Duration(bytes)).toBeCloseTo(seconds(length ?? ""), 0);

  expect(errors).toEqual([]);
});
