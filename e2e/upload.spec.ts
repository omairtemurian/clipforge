import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-64-${index}.png`, import.meta.url),
  );
}

test("a picked video uploads in chunks with progress, then opens its project", async ({
  page,
  request,
}) => {
  test.setTimeout(240_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  let releaseChunk: () => void = () => {};
  const chunkHeld = new Promise<void>((resolve) => (releaseChunk = resolve));
  await page.route(
    /\/api\/uploads\/[0-9a-f]{32}\?offset=\d+$/,
    async (route) => {
      await chunkHeld;
      await route.continue();
    },
  );

  await page.goto("/");
  await page.getByLabel("Upload a video file").setInputFiles(SAMPLE);
  const settings = page.getByRole("dialog", { name: "Clip settings" });
  await settings.getByLabel("Source rights").selectOption("own");
  await settings.getByRole("button", { name: "Get clips" }).click();

  await expect(settings.getByText("Uploading 0%")).toBeVisible();
  await expect(
    settings.getByRole("progressbar", { name: "Upload progress" }),
  ).toBeVisible();
  await page.screenshot({ path: screenshot(1) });
  releaseChunk();

  await expect(page).toHaveURL(/\/projects\/\d+$/);
  const projectId = page.url().split("/").pop();
  const project = await (
    await request.get(`/api/projects/${projectId}`)
  ).json();
  expect(project.source_path).toMatch(/uploads\/[0-9a-f]{32}\/sample\.mp4$/);
  await page.screenshot({ path: screenshot(2) });
  expect(errors).toEqual([]);

  await expect
    .poll(
      async () =>
        (await (await request.get(`/api/projects/${projectId}`)).json()).status,
      { timeout: 180_000, intervals: [1000] },
    )
    .toMatch(/^(done|failed)$/);
  expect((await request.delete(`/api/projects/${projectId}`)).status()).toBe(
    204,
  );
});
