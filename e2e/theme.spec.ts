import { expect, test, type Page } from "@playwright/test";

const LIGHT_BG = "rgb(245, 245, 247)";

/** Record whether <html> is dark at every class change from the first byte. */
async function recordThemeChanges(page: Page) {
  await page.addInitScript(() => {
    const seen: boolean[] = [];
    (window as unknown as { __themeSeen: boolean[] }).__themeSeen = seen;
    // <html> may not exist yet when init scripts run, so watch the document.
    new MutationObserver((records) => {
      for (const record of records) {
        if (record.target === document.documentElement) {
          seen.push(document.documentElement.classList.contains("dark"));
        }
      }
    }).observe(document, {
      attributes: true,
      attributeFilter: ["class"],
      subtree: true,
    });
  });
}

function themeChanges(page: Page) {
  return page.evaluate(
    () => (window as unknown as { __themeSeen: boolean[] }).__themeSeen,
  );
}

function bodyBackground(page: Page) {
  return page.evaluate(() => getComputedStyle(document.body).backgroundColor);
}

test("a fresh profile paints light, the sidebar toggle switches to dark and it sticks", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await recordThemeChanges(page);

  await page.goto("/");
  await expect(
    page.getByRole("link", { name: "Home", exact: true }),
  ).toBeVisible();
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  expect(await bodyBackground(page)).toBe(LIGHT_BG);
  expect(await themeChanges(page)).not.toContain(true);

  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  expect(await bodyBackground(page)).not.toBe(LIGHT_BG);

  await page.reload();
  await expect(
    page.getByRole("link", { name: "Home", exact: true }),
  ).toBeVisible();
  await expect(page.locator("html")).toHaveClass(/dark/);
  // Never light between the first byte and the painted app.
  const changes = await themeChanges(page);
  expect(changes.length).toBeGreaterThan(0);
  expect(changes).not.toContain(false);
  await expect(
    page.getByRole("button", { name: "Switch to light theme" }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("System in Settings -> Appearance follows the OS", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/settings");

  await page.getByRole("radio", { name: "System" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);

  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  expect(await bodyBackground(page)).toBe(LIGHT_BG);
});
