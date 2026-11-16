import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);
const PIPELINE_TIMEOUT = 180_000;

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-76-${index}.png`, import.meta.url),
  );
}

const CHAPTERS = [
  { id: 1, start: 0, end: 25, title: "The setup", summary: "Who is talking." },
  { id: 2, start: 25, end: 60, title: "The pitch", summary: "What it costs." },
];

let projectId: string | undefined;

test.afterEach(async ({ request }) => {
  if (projectId === undefined) return;
  await expect
    .poll(
      async () =>
        (await (await request.get(`/api/projects/${projectId}`)).json()).status,
      { timeout: PIPELINE_TIMEOUT, intervals: [1000] },
    )
    .toMatch(/^(done|failed)$/);
  expect((await request.delete(`/api/projects/${projectId}`)).status()).toBe(
    204,
  );
  projectId = undefined;
});

test("a finished project can be reprompted and its topics chosen", async ({
  page,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT * 2);
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
  const heading = page.getByRole("heading", { name: /^Clips \(\d+\)$/ });
  await expect(heading).toBeVisible({ timeout: PIPELINE_TIMEOUT });

  await page.getByRole("button", { name: "Reprompt" }).click();
  const reprompt = page.getByRole("dialog", { name: "Reprompt" });
  await reprompt.getByLabel("Find moments about").fill("the funniest moment");
  await page.screenshot({ path: screenshot(1) });
  await reprompt.getByRole("button", { name: "Find clips" }).click();
  await expect(reprompt).toBeHidden();
  await expect(page.getByLabel("Result")).toBeVisible({
    timeout: PIPELINE_TIMEOUT,
  });
  await expect(heading).toBeVisible();

  // The recorded LLM only answers curate, so the chapters are canned.
  let made = false;
  await page.route(`**/api/projects/${projectId}/chapters`, (route) =>
    route.fulfill({
      json: route.request().method() === "POST" || made ? CHAPTERS : [],
    }),
  );
  await page.getByRole("button", { name: "Topics" }).click();
  const topics = page.getByRole("dialog", { name: "Topics" });
  made = false;
  await topics.getByRole("button", { name: "Find topics" }).click();
  await topics.getByLabel("The pitch").check();
  await expect(
    topics.getByRole("button", { name: "Clip selected topics (1)" }),
  ).toBeEnabled();
  await page.screenshot({ path: screenshot(2) });

  expect(errors).toEqual([]);
});
