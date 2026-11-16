import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

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
    new URL(`../.agent/screenshots/TASK-100-${index}.png`, import.meta.url),
  );
}

/** Upload the fixture, get clips and open the first clip's editor. */
async function openEditor(page: Page): Promise<string> {
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

test("editor keys: delete, autosave, server undo, copy/paste, speed, versions", async ({
  page,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 60_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  const clipId = await openEditor(page);
  const hookItem = {
    id: "Hook",
    kind: "text",
    asset_id: null,
    start: 0.5,
    end: 2,
    props: { text: "Hook" },
  };
  const seeded = await page.request.patch(`/api/clips/${clipId}/tracks`, {
    data: { text: [hookItem] },
  });
  expect(seeded.status()).toBe(200);
  await page.reload();
  const textItems = () =>
    page.request
      .get(`/api/clips/${clipId}`)
      .then(async (response) => (await response.json()).tracks.text.length);
  const status = page.getByRole("status", { name: "Autosave status" });
  const textTrack = page.getByRole("group", { name: "Text track" });
  const hook = textTrack.getByRole("button", { name: /^Text: Hook,/ });

  // Delete the selected item; autosave saves it.
  await hook.click();
  await expect(hook).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Delete");
  await expect(textTrack.getByRole("button")).toHaveCount(0);
  await expect(status).toHaveText("All changes saved", { timeout: 10_000 });
  await expect.poll(textItems).toBe(0);

  // The edit is saved: cmd+Z undoes it on the server.
  await page.keyboard.press("ControlOrMeta+z");
  await expect(hook).toBeVisible();
  await expect.poll(textItems).toBe(1);

  // Copy the item and paste it at the playhead.
  await hook.click();
  await page.keyboard.press("ControlOrMeta+c");
  await page.keyboard.press("ControlOrMeta+v");
  await expect(textTrack.getByRole("button")).toHaveCount(2);
  await expect(
    textTrack.getByRole("button", { name: "Text: Hook, 00:00.00 - 00:01.50" }),
  ).toHaveAttribute("aria-pressed", "true");

  // Playback speed with > and the menu.
  await page.keyboard.press(">");
  const speed = page.getByRole("combobox", { name: "Playback speed" });
  await expect(speed).toHaveValue("1.25");
  await expect(status).toHaveText("All changes saved", { timeout: 10_000 });
  await expect.poll(textItems).toBe(2);
  await page.screenshot({ path: screenshot(1), animations: "disabled" });

  // The version list: restore the first version (no text items).
  await page.getByRole("button", { name: "Version history" }).click();
  const dialog = page.getByRole("dialog", { name: "Version history" });
  const versions = dialog.getByRole("listitem");
  await expect(versions.first()).toContainText("Current");
  await expect(versions.last()).toContainText("Original clip");
  await page.screenshot({ path: screenshot(2), animations: "disabled" });
  await versions.last().getByRole("button", { name: "Restore" }).click();
  await expect(dialog).toBeHidden();
  await expect(textTrack.getByRole("button")).toHaveCount(0);
  await expect.poll(textItems).toBe(0);
  await expect(status).toHaveText("All changes saved");
  await page.screenshot({ path: screenshot(3), animations: "disabled" });

  expect(errors).toEqual([]);
});
