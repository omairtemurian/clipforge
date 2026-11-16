import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);
const PIPELINE_TIMEOUT = 180_000;
// A 1x1 PNG: the API only checks the image's magic bytes.
const PROOF = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

let projectId: string | undefined;

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-175-${index}.png`, import.meta.url),
  );
}

test.afterEach(async ({ request }) => {
  if (projectId !== undefined) {
    expect((await request.delete(`/api/projects/${projectId}`)).status()).toBe(
      204,
    );
    projectId = undefined;
  }
  const campaigns = await (await request.get("/api/campaigns")).json();
  for (const { id } of campaigns as { id: number }[]) {
    await request.delete(`/api/campaigns/${id}`);
  }
});

/** Upload the fixture from Home with the source rights "own" and wait for its clips. */
async function getClips(page: Page): Promise<void> {
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
}

test("create a campaign, apply it to a project and read the rule check", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  await page.goto("/");
  await page.getByRole("link", { name: "Campaigns" }).click();
  const form = page.getByRole("form", { name: "New campaign" });
  await form.getByLabel("Name").fill("Spring clips");
  await form.getByLabel("Creator", { exact: true }).fill("Afro");
  await form.getByRole("checkbox", { name: "YouTube" }).check();
  await form.getByLabel("Required hashtags").fill("#clipforge #spring");
  await form.getByLabel("Required credit line").fill("Clip from Afro");
  await form.getByLabel("Maximum length (s)").fill("5");
  await form
    .getByLabel("Permission source link")
    .fill("https://example.com/permission");
  await form
    .getByLabel("Permission screenshot")
    .setInputFiles({ name: "proof.png", mimeType: "image/png", buffer: PROOF });
  await form.getByRole("button", { name: "Create campaign" }).click();

  const saved = page.getByRole("form", { name: "Edit Spring clips" });
  await expect(saved.getByText(/Complete, saved .* is allowed/)).toBeVisible();
  await page
    .getByRole("heading", { name: "Campaigns", level: 1 })
    .scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(1) });

  await getClips(page);
  await page.getByLabel("Campaign", { exact: true }).selectOption({
    label: "Spring clips",
  });
  await expect(
    page.getByText("Campaign applied to the project and its clips."),
  ).toBeVisible();
  await expect(page.getByRole("article").first()).toContainText("Clip from Afro");
  await page.screenshot({ path: screenshot(2) });

  await page
    .getByRole("article")
    .first()
    .getByRole("link", { name: "Edit clip" })
    .click();
  await page.getByRole("button", { name: "Rules" }).click();
  const panel = page.getByRole("complementary", { name: "Rules panel" });
  await expect(
    panel.getByRole("listitem", { name: "Required hashtags: pass" }),
  ).toBeVisible();
  await expect(
    panel.getByRole("listitem", { name: "Maximum length: fail" }),
  ).toBeVisible();
  await expect(panel.getByRole("status")).toContainText(
    "Publishing is blocked",
  );
  await page.screenshot({ path: screenshot(3) });
  expect(errors).toEqual([]);
});
