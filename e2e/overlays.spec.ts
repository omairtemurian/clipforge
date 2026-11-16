import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { saveChanges, turnAutosaveOff } from "./autosave";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);
const PIPELINE_TIMEOUT = 180_000;

test.use({ viewport: { width: 1440, height: 900 } });

let projectId: string | undefined;
let mediaId: number | undefined;

test.afterEach(async ({ request }) => {
  if (projectId !== undefined) {
    const response = await request.delete(`/api/projects/${projectId}`);
    expect(response.status()).toBe(204);
    projectId = undefined;
  }
  // The library is global: free logo.png so a re-run can upload it again.
  if (mediaId !== undefined) {
    const response = await request.delete(`/api/library/${mediaId}`);
    expect(response.status()).toBe(204);
    mediaId = undefined;
  }
});

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-107-${index}.png`, import.meta.url),
  );
}

/** A 320x180 orange PNG made by ffmpeg, as bytes. */
function logoPng(): Buffer {
  const dir = mkdtempSync(join(tmpdir(), "clipforge-e2e-"));
  try {
    const path = join(dir, "logo.png");
    execFileSync("ffmpeg", [
      "-loglevel",
      "error",
      "-f",
      "lavfi",
      "-i",
      "color=c=orange:s=320x180",
      "-frames:v",
      "1",
      path,
    ]);
    return readFileSync(path);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

/** Upload the fixture, get clips and open the first clip's editor. */
async function openEditor(page: Page): Promise<string> {
  await turnAutosaveOff(page);
  await page.goto("/");
  await page.getByLabel("Upload a video file").setInputFiles(SAMPLE);
  const settings = page.getByRole("dialog", { name: "Clip settings" });
  await settings.getByLabel("Source rights").selectOption("own");
  await settings.getByRole("button", { name: "Get clips" }).click();
  await expect(page).toHaveURL(/\/projects\/\d+$/);
  projectId = page.url().split("/").pop();
  await expect(
    page.getByRole("heading", { name: /^Clips \(\d+\)$/ }),
  ).toBeVisible({ timeout: PIPELINE_TIMEOUT });
  await page
    .getByRole("article")
    .first()
    .getByRole("link", { name: "Edit clip" })
    .click();
  await expect(page).toHaveURL(/\/clips\/\d+$/);
  return page.url().split("/").pop()!;
}

test("editor: drag media onto the timeline, add a text layer, pick transitions", async ({
  page,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 60_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  const upload = await page.request.post("/api/library", {
    multipart: {
      file: { name: "logo.png", mimeType: "image/png", buffer: logoPng() },
    },
  });
  expect(upload.status()).toBe(201);
  mediaId = (await upload.json()).asset.id;
  const clipId = await openEditor(page);

  // Media: drag the logo onto the Overlays track.
  await page.getByRole("button", { name: "Media", exact: true }).click();
  const tile = page.getByLabel("Drag logo.png onto the timeline");
  await expect(tile).toBeVisible();
  const overlays = page.getByRole("group", { name: "Overlays track" });
  await tile.dragTo(overlays, { targetPosition: { x: 40, y: 8 } });
  await expect(
    overlays.getByRole("button", { name: /^Overlays: Image #\d+,/ }),
  ).toBeVisible();
  await page.screenshot({ path: screenshot(1), animations: "disabled" });

  // Text layers: add one at the playhead and style it.
  await page.getByRole("button", { name: "Text layers" }).click();
  await page.getByRole("button", { name: "Add text" }).click();
  const text = page.getByLabel("Text", { exact: true });
  await text.fill("Big news");
  await page.getByLabel("Animation in", { exact: true }).selectOption("pop");
  await page.getByRole("switch", { name: "Background box" }).click();
  await expect(
    page
      .getByRole("group", { name: "Text track" })
      .getByRole("button", { name: /^Text: Big news,/ }),
  ).toBeVisible();
  await page
    .getByRole("complementary", { name: "Text layers panel" })
    .evaluate((panel) => panel.scrollTo(0, 0));
  await page.screenshot({ path: screenshot(2), animations: "disabled" });

  // Transitions: a crossfade at jump cuts.
  await page.getByRole("button", { name: "Transitions" }).click();
  await page
    .getByLabel("At jump cuts", { exact: true })
    .selectOption("crossfade");
  await expect(
    page.getByRole("slider", { name: "At jump cuts length" }),
  ).toBeVisible();
  await page.screenshot({ path: screenshot(3), animations: "disabled" });

  await saveChanges(page, { tracks: true });
  await expect(
    page.getByRole("button", { name: "Save changes" }),
  ).toBeDisabled();
  const saved = await (await page.request.get(`/api/clips/${clipId}`)).json();
  expect(saved.tracks.overlays).toHaveLength(1);
  expect(saved.tracks.overlays[0].kind).toBe("image");
  expect(saved.tracks.text[0].props).toMatchObject({
    text: "Big news",
    animation_in: "pop",
    box: "#000000",
  });
  expect(saved.transitions.auto).toEqual({ kind: "crossfade", duration: 0.3 });
  expect(errors).toEqual([]);
});
