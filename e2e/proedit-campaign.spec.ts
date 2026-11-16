import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

/** Where screenshot index of this check is saved. */
function screenshot(index: number): string {
  return fileURLToPath(
    new URL(`../.agent/screenshots/TASK-232-${index}.png`, import.meta.url),
  );
}

test.afterEach(async ({ request }) => {
  const campaigns = await (await request.get("/api/campaigns")).json();
  for (const { id } of campaigns as { id: number }[]) {
    await request.delete(`/api/campaigns/${id}`);
  }
});

test("a campaign's Pro Edit variant switch, preset, intensity and heavy edits are saved", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  const created = await request.post("/api/campaigns", {
    data: { name: "Spring clips", rate_per_1k_usd: 1.5 },
  });
  const campaignId = ((await created.json()) as { id: number }).id;

  await page.goto("/campaigns");
  const section = page.getByRole("region", { name: "Pro Edit" });
  const toggle = section.getByRole("switch", {
    name: "Also make a Pro Edit variant",
  });
  await expect(toggle).not.toBeChecked();
  await toggle.click();
  await expect(section.getByRole("status")).toContainText(
    "No variant is made while heavy edits are not allowed",
  );
  await section
    .getByLabel("Heavy edits allowed (allow_heavy_edits)")
    .selectOption("true");
  await section.getByLabel("Pro Edit preset").selectOption("skull_moment");
  await section.getByLabel("Maximum intensity").selectOption("pro");
  await expect(toggle).toBeChecked();
  await expect(
    section.getByRole("button", { name: "Save Pro Edit settings" }),
  ).toBeEnabled();
  await section.scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(1) });
  await section.getByRole("button", { name: "Save Pro Edit settings" }).click();
  await expect(
    section.getByRole("button", { name: "Save Pro Edit settings" }),
  ).toBeDisabled();

  const settings = await (
    await request.get(`/api/campaigns/${campaignId}/autopilot`)
  ).json();
  expect(settings).toMatchObject({
    enabled: false,
    proedit_enabled: true,
    proedit_preset: "skull_moment",
    proedit_max_intensity: "pro",
  });
  const campaign = await (
    await request.get(`/api/campaigns/${campaignId}`)
  ).json();
  expect(campaign.allow_heavy_edits).toBe("true");

  await page.reload();
  await expect(
    page
      .getByRole("region", { name: "Pro Edit" })
      .getByRole("switch", { name: "Also make a Pro Edit variant" }),
  ).toBeChecked();
  await expect(
    page
      .getByRole("region", { name: "Pro Edit" })
      .getByLabel("Pro Edit preset"),
  ).toHaveValue("skull_moment");
  await page.getByRole("region", { name: "Pro Edit" }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(2) });
  expect(errors).toEqual([]);
});
