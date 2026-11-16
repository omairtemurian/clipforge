import { expect, test } from "@playwright/test";

test("home loads without console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: "ClipForge", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("the API behind the page is the test-mode backend with no projects", async ({
  request,
}) => {
  const response = await request.get("/api/projects");

  expect(response.ok()).toBe(true);
  expect(await response.json()).toEqual([]);
});
