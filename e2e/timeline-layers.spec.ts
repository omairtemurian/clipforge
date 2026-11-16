import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { turnAutosaveOff } from "./autosave";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);
const PIPELINE_TIMEOUT = 180_000;

test.use({ viewport: { width: 1440, height: 900 } });

let projectId: string | undefined;

test.afterEach(async ({ request }) => {
  if (projectId === undefined) return;
  const response = await request.delete(`/api/projects/${projectId}`);
  expect(response.status()).toBe(204);
  projectId = undefined;
});

/** Where the screenshot number index of this check is saved. */
function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-99-${index}.png`, import.meta.url),
  );
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

function textItem(id: string, start: number, end: number) {
  return { id, kind: "text", asset_id: null, start, end, props: { text: id } };
}

test("timeline: layer tracks, drag an item with snapping and save it", async ({
  page,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 60_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  const clipId = await openEditor(page);
  const tracks = await page.request.patch(`/api/clips/${clipId}/tracks`, {
    data: { text: [textItem("Hook", 0.5, 2), textItem("Big number", 3, 4.5)] },
  });
  expect(tracks.status()).toBe(200);
  await page.reload();

  for (const name of ["B-roll", "Overlays", "Text", "Music", "SFX"]) {
    await expect(
      page.getByRole("group", { name: `${name} track` }),
    ).toBeVisible();
  }
  await expect(
    page.getByRole("group", { name: "Voiceover track" }),
  ).toBeVisible();
  const textTrack = page.getByRole("group", { name: "Text track" });
  const hook = textTrack.getByRole("button", { name: /^Text: Hook,/ });
  await expect(hook).toHaveAccessibleName("Text: Hook, 00:00.50 - 00:02.00");
  await page.screenshot({ path: screenshot(1), animations: "disabled" });

  // Drag "Hook" right, onto "Big number": its end snaps to that item's start.
  const box = (await hook.boundingBox())!;
  const other = (await textTrack
    .getByRole("button", { name: /^Text: Big number,/ })
    .boundingBox())!;
  const y = box.y + box.height / 2;
  await page.mouse.move(box.x + box.width / 2, y);
  await page.mouse.down();
  const target = other.x - box.width / 2 - 3;
  await page.mouse.move(target, y, { steps: 8 });
  await page.mouse.up();
  await expect(hook).not.toHaveAccessibleName(
    "Text: Hook, 00:00.50 - 00:02.00",
  );
  await page.screenshot({ path: screenshot(2), animations: "disabled" });

  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(
    page.getByRole("button", { name: "Save changes" }),
  ).toBeDisabled();
  const fetchClip = async () =>
    (await page.request.get(`/api/clips/${clipId}`)).json();
  await expect
    .poll(async () => (await fetchClip()).tracks.text[0].start)
    .not.toBe(0.5);
  const saved = await fetchClip();
  const moved = saved.tracks.text[0];
  expect(moved.id).toBe("Hook");
  expect(moved.end - moved.start).toBeCloseTo(1.5, 3);
  // An edge snapped (8 px) to "Big number"'s start, a segment edge or a
  // word edge.
  const words: { start: number; end: number }[] = await (
    await page.request.get(`/api/clips/${clipId}/transcript`)
  ).json();
  const cuts: [number, number][] = saved.cut_ranges;
  const toClip = (t: number) => {
    const source = Math.min(Math.max(t, saved.start), saved.end);
    const removed = cuts
      .filter(([from]) => from < source)
      .reduce((sum, [from, to]) => sum + Math.min(source, to) - from, 0);
    return Math.round((source - saved.start - removed) * 1000) / 1000;
  };
  // Segment edges: cuts, splits and scene edges ("Segment 00:01.00 - ...").
  const seconds = (code: string) => {
    const [minutes, rest] = code.split(":");
    return Number(minutes) * 60 + Number(rest);
  };
  const segments = (
    await page
      .getByRole("button", { name: /^Segment / })
      .evaluateAll((buttons) =>
        buttons.map((button) => button.getAttribute("aria-label") ?? ""),
      )
  ).flatMap((label) => label.replace("Segment ", "").split(" - ").map(seconds));
  const targets = [
    3,
    ...cuts.flat().map(toClip),
    ...segments.map(toClip),
    ...words.flatMap((word) => [word.start, word.end]).map(toClip),
  ];
  // A moved item snaps by whichever of its edges is nearer a target.
  expect(targets.includes(moved.start) || targets.includes(moved.end)).toBe(
    true,
  );
  expect(moved.start).toBeGreaterThan(1);
  expect(errors).toEqual([]);
});
