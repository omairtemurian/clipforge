import { expect, test, type APIRequestContext } from "@playwright/test";
import { fileURLToPath } from "node:url";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);
const PIPELINE_TIMEOUT = 180_000;

/** Where the screenshot number index of this check is saved. */
function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/fix-projects-${index}.png`, import.meta.url),
  );
}

let projectId: string | undefined;

/** Wait until the project's processing ended; a running one cannot be deleted. */
async function waitUntilEnded(request: APIRequestContext, id: string) {
  await expect
    .poll(
      async () =>
        (await (await request.get(`/api/projects/${id}`)).json()).status,
      { timeout: PIPELINE_TIMEOUT, intervals: [1000] },
    )
    .toMatch(/^(done|failed)$/);
}

test.afterEach(async ({ request }) => {
  if (projectId === undefined) return;
  await waitUntilEnded(request, projectId);
  const response = await request.delete(`/api/projects/${projectId}`);
  expect(response.status()).toBe(204);
  projectId = undefined;
});

test("a running project can be reopened from the Projects page", async ({
  page,
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
  await settings.getByLabel("Source rights").selectOption("own");
  await settings.getByRole("button", { name: "Get clips" }).click();
  await expect(page).toHaveURL(/\/projects\/\d+$/);
  projectId = page.url().split("/").pop();

  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();

  await page.getByRole("link", { name: /^Projects, 1 in progress$/ }).click();
  const card = page.getByRole("article");
  await expect(card).toHaveCount(1);
  await expect(card.getByRole("progressbar")).toBeVisible();
  // Let the sidebar links' color transition (150 ms) end before the shot.
  await page.waitForTimeout(300);
  await page.screenshot({
    path: screenshot(1),
    fullPage: true,
  });

  await card.getByRole("link", { name: /^Open / }).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}$`));
  await expect(
    page.getByRole("progressbar", { name: "Overall progress" }),
  ).toBeVisible();
  await page.screenshot({
    path: screenshot(2),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
