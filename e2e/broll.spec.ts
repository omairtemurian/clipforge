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

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-121-${index}.png`, import.meta.url),
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

const THUMB = `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ff6b35"/><stop offset="1" stop-color="#27272a"/></linearGradient></defs><rect width="320" height="180" fill="url(#g)"/></svg>`;

function stock(id: string, creator: string) {
  return {
    provider: "pexels",
    provider_id: id,
    page_url: `https://www.pexels.com/video/${id}/`,
    preview_url: `/e2e-stock/${id}.svg`,
    download_url: `https://videos.pexels.com/${id}.mp4`,
    width: 1080,
    height: 1920,
    duration_s: 12,
    creator,
    creator_url: null,
    tags: [],
    license: "Pexels License",
    attribution: `Video by ${creator} on Pexels`,
  };
}

test("editor: review B-roll spots with thumbnails and attribution", async ({
  page,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 60_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  // Test mode has no stock API key and its recorded LLM cannot pick spots.
  await page.route("**/api/broll/providers", (route) =>
    route.fulfill({
      json: [
        { provider: "pexels", label: "Pexels", enabled: true, message: "" },
      ],
    }),
  );
  await page.route("**/api/clips/*/broll/spots", (route) =>
    route.fulfill({
      json: [
        {
          sentence: 0,
          text: "A man and a whole pizza",
          start: 0.5,
          end: 3,
          keywords: ["pizza"],
          query: "pizza",
          results: [stock("101", "Ana"), stock("102", "Ben")],
          error: null,
        },
      ],
    }),
  );
  await page.route("**/e2e-stock/*.svg", (route) =>
    route.fulfill({ body: THUMB, contentType: "image/svg+xml" }),
  );

  await openEditor(page);
  await page.getByRole("button", { name: "B-roll", exact: true }).click();
  const panel = page.getByRole("complementary", { name: "B-roll panel" });
  await panel.getByRole("button", { name: "Find B-roll spots" }).click();

  const spots = panel.getByRole("list", { name: "B-roll spots" });
  await expect(spots.getByText("“A man and a whole pizza”")).toBeVisible();
  await expect(spots.getByText("Video by Ana on Pexels")).toBeVisible();
  await expect(spots.getByText(/Pexels License/).first()).toBeVisible();
  await expect(spots.locator("img").first()).toBeVisible();
  await spots.scrollIntoViewIfNeeded();
  await panel.evaluate((el) => el.scrollTo(0, el.scrollHeight));
  await page.screenshot({ path: screenshot(1), animations: "disabled" });
  expect(errors).toEqual([]);
});
