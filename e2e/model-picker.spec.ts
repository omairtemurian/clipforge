import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

function screenshot(index: number): string {
  return fileURLToPath(
    new URL(
      `../.agent/screenshots/steering-model-picker-${index}.png`,
      import.meta.url,
    ),
  );
}

test("the model is picked from the provider's list and saved after a trial", async ({
  page,
}) => {
  const problems: string[] = [];
  page.on("pageerror", (error) => problems.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") problems.push(message.text());
  });

  await page.goto("/settings");
  const llm = page.getByRole("region", { name: "Language model" });
  await llm.getByRole("radio", { name: "OpenAI-compatible" }).click();

  const model = llm.getByRole("combobox", { name: "Model" });
  await expect(model).toBeVisible();
  await expect(model.locator("option")).toHaveText([
    "test-model-a",
    "test-model-b",
    "Custom…",
  ]);
  await model.selectOption("test-model-b");
  await model.scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot(1) });

  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Settings saved.")).toBeVisible();

  await page.reload();
  await expect(
    llm.getByRole("radio", { name: "OpenAI-compatible" }),
  ).toBeChecked();
  await expect(llm.getByRole("combobox", { name: "Model" })).toHaveValue(
    "test-model-b",
  );

  await llm.getByRole("radio", { name: "GitHub Copilot" }).click();
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Settings saved.").first()).toBeVisible();
  expect(problems).toEqual([]);
});
