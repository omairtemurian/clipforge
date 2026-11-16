import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(
      `../.agent/screenshots/steering-agents-${index}.png`,
      import.meta.url,
    ),
  );
}

test("AI agents & API: make a key, copy an MCP config, see the agent connect", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/settings");

  await page
    .getByRole("navigation", { name: "Settings pages" })
    .getByRole("link", { name: "AI agents & API" })
    .click();
  await expect(
    page.getByRole("heading", { name: "AI agents & API", level: 1 }),
  ).toBeVisible();
  await expect(page.getByText(/only you can publish/)).toBeVisible();
  await expect(
    page.getByText(/No agent connected in the last 7 days/),
  ).toBeVisible();

  await page.getByLabel("Key name").fill("Hermes on my Mac");
  await page.getByRole("button", { name: "Create key" }).click();
  const secret = page.getByLabel('API key "Hermes on my Mac"', { exact: true });
  await expect(secret).toBeVisible();
  const key = (await secret.textContent()) ?? "";
  expect(key).toMatch(/^cfk_/);
  const hermes = page.getByLabel("Add with the Hermes CLI", { exact: true });
  await expect(hermes).toContainText(`CLIPFORGE_API_KEY=${key}`);
  await expect(hermes).toContainText("clipforge-mcp");

  await page
    .getByRole("button", { name: "Copy Add with the Hermes CLI" })
    .click();
  await expect(page.getByText("Copied")).toBeVisible();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toMatch(
    /^hermes mcp add clipforge \\\n {2}--command uv \\\n {2}--env /,
  );
  await page
    .getByRole("heading", { name: "AI agents & API", level: 1 })
    .scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(1) });
  await hermes.scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(2) });

  const answer = await page.request.get(
    "http://127.0.0.1:8000/api/v1/projects",
    {
      headers: { "X-API-Key": key },
    },
  );
  expect(answer.status()).toBe(200);
  await page.reload();
  await expect(page.getByText("Hermes on my Mac · just now")).toBeVisible();
  await expect(page.getByText(/Last used just now/)).toBeVisible();

  await page.getByRole("tab", { name: "Claude Desktop" }).click();
  await expect(
    page.getByLabel("claude_desktop_config.json", { exact: true }),
  ).toContainText('"mcpServers"');

  await page.getByLabel("Webhook URL").fill("http://localhost:5678/webhook/cf");
  await page.getByRole("button", { name: "Add webhook" }).click();
  await expect(
    page.getByLabel("Webhook secret", { exact: true }),
  ).toContainText("whsec_");
  await expect(
    page
      .getByRole("list", { name: "Webhooks" })
      .getByText("http://localhost:5678/webhook/cf"),
  ).toBeVisible();
  await page.screenshot({ path: screenshot(3) });

  await page.getByRole("button", { name: "Revoke Hermes on my Mac" }).click();
  await page.getByRole("button", { name: "Revoke Hermes on my Mac" }).click();
  await expect(page.getByRole("list", { name: "API keys" })).toBeHidden();
  const revoked = await page.request.get(
    "http://127.0.0.1:8000/api/v1/projects",
    {
      headers: { "X-API-Key": key },
    },
  );
  expect(revoked.status()).toBe(401);
  expect(errors).toEqual([]);
});
