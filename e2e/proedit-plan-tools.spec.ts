import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";
import {
  PIPELINE_TIMEOUT,
  PRO_EDIT_TIMEOUT,
  uploadAndMakeVariant,
} from "./proedit-flow";

/** Where screenshot index of this check is saved. */
function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-227-${index}.png`, import.meta.url),
  );
}

let projectId: string | undefined;

test.afterEach(async ({ request }) => {
  if (projectId === undefined) return;
  await request.delete(`/api/projects/${projectId}`);
  projectId = undefined;
});

test("inspect an item, read the plan versions and critic, reset to v1", async ({
  page,
  request,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + PRO_EDIT_TIMEOUT + 60_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  const ids = await uploadAndMakeVariant(page, request);
  projectId = ids.projectId;
  const { originalId, variantId } = ids;

  // Version 2: the last item removed (stored as the next plan version).
  const plan = (await (
    await request.get(`/api/proedit/clips/${variantId}/plan`)
  ).json()) as { items: unknown[] };
  const patched = await request.patch(`/api/proedit/clips/${variantId}/plan`, {
    data: { items: plan.items.slice(0, -1) },
  });
  expect(patched.ok()).toBe(true);

  // The critic ran on version 1 in the real app only with a vision model;
  // its verdict is a recorded one here.
  await page.route(`**/api/proedit/clips/${variantId}/runs`, async (route) => {
    const runs = (await (await route.fetch()).json()) as Record<
      string,
      unknown
    >[];
    runs[0] = {
      ...runs[0],
      rounds: 1,
      critic_scores: [
        {
          round: 1,
          plan_version: 1,
          scores: [
            { check: "Hook strength", score: 5, reason: "The hook is soft." },
            { check: "Dead air", score: 9, reason: "No gaps." },
          ],
          changes: [],
          ignored: [],
          notes: ["Stopped: the model could not see the frames."],
        },
      ],
    };
    await route.fulfill({ json: runs });
  });

  await page.goto(`/clips/${originalId}/proedit`);
  const lanes = page.getByRole("region", { name: "EDL lanes" });
  await expect(page.getByLabel("Plan version")).toContainText("Plan v2");

  const versions = page.getByRole("region", { name: "Version history" });
  await expect(
    versions.getByRole("list", { name: "Changes from v1" }),
  ).toContainText("Removed");
  const critic = page.getByRole("region", { name: "Critic", exact: true });
  await expect(critic).toContainText("Hook strength");
  await expect(critic).toContainText("5/10");

  // Selecting an item opens its parameters in the inspector.
  await lanes.getByTestId("edl-item").first().focus();
  const inspector = page.getByRole("region", { name: "Inspector" });
  await expect(inspector.getByRole("heading")).toContainText("parameters");
  await versions.scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(1), animations: "disabled" });

  // Reset stores a copy of v1 as version 3 and says what it brought back.
  await page.getByRole("button", { name: "Reset to plan v1" }).click();
  await expect(page.getByLabel("Plan version")).toContainText("Plan v3");
  await expect(
    versions.getByRole("list", { name: "Changes from v2" }),
  ).toContainText("Added");
  await expect(
    page.getByRole("button", { name: "Render plan v3" }),
  ).toBeVisible();
  await page.screenshot({ path: screenshot(2), animations: "disabled" });

  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.screenshot({ path: screenshot(3), animations: "disabled" });

  expect(errors).toEqual([]);
});
