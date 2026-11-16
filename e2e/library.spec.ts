import { expect, test, type APIRequestContext } from "@playwright/test";
import { fileURLToPath } from "node:url";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);
const PIPELINE_TIMEOUT = 180_000;

/** Where the screenshot number index of this task is saved. */
function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-156-${index}.png`, import.meta.url),
  );
}

let projectId: string | undefined;
let collectionId: string | undefined;

/** Wait until the project's processing ended. */
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
  if (collectionId !== undefined) {
    await request.delete(`/api/collections/${collectionId}`);
    collectionId = undefined;
  }
  if (projectId === undefined) return;
  await waitUntilEnded(request, projectId);
  await expect
    .poll(
      async () => (await request.delete(`/api/projects/${projectId}`)).status(),
      {
        timeout: 60_000,
        intervals: [1000],
      },
    )
    .toBe(204);
  projectId = undefined;
});

test("search finds a moment, clips it, exports it and storage cleans up", async ({
  page,
  request,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + 120_000);
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
  projectId = page.url().split("/").pop()!;
  await waitUntilEnded(request, projectId);

  // Projects: the status chips narrow the list.
  await page.goto("/projects");
  const status = page.getByRole("radiogroup", { name: "Status" });
  await status.getByRole("radio", { name: "Failed" }).click();
  await expect(page.getByText("No failed projects.")).toBeVisible();
  await status.getByRole("radio", { name: "Ready" }).click();
  await expect(page.getByRole("article")).toHaveCount(1);
  await page.waitForTimeout(300);
  await page.screenshot({ path: screenshot(1), fullPage: true });

  // The top bar searches the transcripts in the Media library.
  const top = page.getByRole("searchbox", {
    name: "Search keywords or moments",
  });
  await top.fill("yoga");
  await top.press("Enter");
  await expect(page).toHaveURL(/\/library\?q=yoga$/);
  const results = page.getByRole("list", { name: "Moments found" });
  await expect(results.locator("mark", { hasText: /yoga/i })).toBeVisible();
  await results
    .getByRole("button", { name: /^Play / })
    .first()
    .click();
  await expect(page.getByLabel(/^Source video of /)).toBeVisible();
  await results
    .getByRole("button", { name: /^Make clip of / })
    .first()
    .click();
  await expect(results.getByRole("link", { name: "Open clip" })).toBeVisible();
  await page.getByRole("button", { name: "Select all" }).click();
  await page.waitForTimeout(300);
  await page.screenshot({ path: screenshot(2), fullPage: true });

  // Bulk export: the selected moments go to a new collection.
  await page.getByRole("button", { name: "Export to collection" }).click();
  const dialog = page.getByRole("dialog", { name: "Add to collection" });
  await expect(dialog.getByLabel("Name", { exact: true })).toHaveValue(
    "Moments: yoga",
  );
  await dialog.getByRole("button", { name: "Add" }).click();
  await expect(page).toHaveURL(/\/collections\?id=\d+$/);
  collectionId = new URL(page.url()).searchParams.get("id")!;
  const clips = page.getByRole("list", { name: "Clips" });
  await expect(clips.getByRole("listitem")).toHaveCount(1);
  await expect(clips.getByText("Rendered", { exact: true })).toBeVisible({
    timeout: 120_000,
  });
  await expect(
    page.getByRole("link", { name: "Download zip" }),
  ).toHaveAttribute("href", `/api/collections/${collectionId}/download.zip`);
  const zip = await request.get(
    `/api/collections/${collectionId}/download.zip`,
  );
  expect(zip.status()).toBe(200);
  await page.waitForTimeout(300);
  await page.screenshot({ path: screenshot(3), fullPage: true });

  // Settings -> Storage: clean up after a confirmation.
  await page.goto("/settings");
  await page
    .getByRole("navigation", { name: "Settings pages" })
    .getByRole("link", { name: "Storage" })
    .click();
  await expect(page.getByRole("heading", { name: "Storage" })).toBeVisible();
  await page.getByRole("button", { name: /^Clean up / }).click();
  const confirm = page.getByRole("alertdialog", {
    name: "Clean up this project?",
  });
  await expect(confirm).toContainText("freeing about");
  await page.waitForTimeout(300);
  await page.screenshot({ path: screenshot(4), fullPage: true });
  await confirm.getByRole("button", { name: "Clean up" }).click();
  await expect(page.getByText(/^Cleaned up\. .* freed\.$/)).toBeVisible();
  await page.screenshot({ path: screenshot(5), fullPage: true });

  expect(errors).toEqual([]);
});
