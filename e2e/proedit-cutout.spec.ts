import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";
import {
  PRO_EDIT_TIMEOUT,
  PIPELINE_TIMEOUT,
  uploadSample,
} from "./proedit-flow";

let projectId: string | undefined;

test.afterEach(async ({ request }) => {
  if (projectId === undefined) return;
  await request.delete(`/api/projects/${projectId}`);
  projectId = undefined;
});

test("a Pro Edit with the subject cut-out renders a variant", async ({
  page,
  request,
}) => {
  test.setTimeout(PIPELINE_TIMEOUT + PRO_EDIT_TIMEOUT + 60_000);
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  const uploaded = await uploadSample(page, request);
  projectId = uploaded.projectId;
  await page
    .getByRole("article")
    .first()
    .getByRole("button", { name: "Pro Edit" })
    .click();
  const dialog = page.getByRole("dialog", { name: "Pro Edit" });
  await dialog.getByText("Skull Moment", { exact: true }).click();
  await dialog.getByRole("switch", { name: "Use critic" }).click();
  const front = dialog.getByRole("switch", {
    name: "Subject in front of text",
  });
  await front.click();
  await expect(front).toBeChecked();
  await dialog.getByLabel("Background", { exact: true }).selectOption("swap");
  await expect(dialog.getByLabel("Background color")).toBeVisible();
  await expect(dialog.getByLabel("Cost estimate")).not.toHaveText(
    "Estimating the cost…",
  );
  await front.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: fileURLToPath(
      new URL("../.agent/screenshots/TASK-234-1.png", import.meta.url),
    ),
    animations: "disabled",
  });

  await dialog.getByRole("button", { name: "Run Pro Edit" }).click();
  await expect(dialog.getByText(/The Pro Edit variant is ready/)).toBeVisible({
    timeout: PRO_EDIT_TIMEOUT,
  });
  const variants = (await (
    await request.get(`/api/proedit/clips/${uploaded.originalId}/variants`)
  ).json()) as { id: number }[];
  expect(variants.length).toBeGreaterThan(0);
  expect(errors).toEqual([]);
});
