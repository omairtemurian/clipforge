import { expect, test, type APIRequestContext } from "@playwright/test";
import { fileURLToPath } from "node:url";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);
const PIPELINE_TIMEOUT = 180_000;

/** Where the screenshot number index of this check is saved. */
function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-79-${index}.png`, import.meta.url),
  );
}

let projectId: string | undefined;

/** The status of a project once its processing has ended. */
async function endedStatus(request: APIRequestContext, id: string) {
  await expect
    .poll(
      async () =>
        (await (await request.get(`/api/projects/${id}`)).json()).status,
      { timeout: PIPELINE_TIMEOUT, intervals: [1000] },
    )
    .toMatch(/^(done|failed)$/);
  return (await (await request.get(`/api/projects/${id}`)).json()).status;
}

test.afterEach(async ({ request }) => {
  if (projectId === undefined) return;
  await endedStatus(request, projectId);
  const response = await request.delete(`/api/projects/${projectId}`);
  expect(response.status()).toBe(204);
  projectId = undefined;
});

test("a project with Clip anything on is processed to the end", async ({
  page,
  request,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 60_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  await page.goto("/");
  await page.getByLabel("Upload a video file").setInputFiles(SAMPLE);
  const settings = page.getByRole("dialog", { name: "Clip settings" });
  const clipAnything = settings.getByRole("switch", { name: "Clip anything" });
  await expect(clipAnything).not.toBeChecked();
  await clipAnything.click();
  await expect(clipAnything).toBeChecked();
  await expect(
    settings.getByRole("switch", { name: "Auto cut silences" }),
  ).toBeDisabled();
  await clipAnything.scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(1) });

  await settings.getByLabel("Source rights").selectOption("own");
  await settings.getByRole("button", { name: "Get clips" }).click();
  await expect(page).toHaveURL(/\/projects\/\d+$/);
  projectId = page.url().split("/").pop()!;

  const project = await (
    await request.get(`/api/projects/${projectId}`)
  ).json();
  expect(project.settings.clip_anything).toBe(true);
  expect(await endedStatus(request, projectId)).toBe("done");
  expect(errors).toEqual([]);
});
