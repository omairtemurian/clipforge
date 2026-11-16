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

test("a Pro Edit with a loop-friendly ending ends on a loop transition", async ({
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
  await dialog.getByText("Phonk Edit", { exact: true }).click();
  await dialog.getByRole("switch", { name: "Use critic" }).click();
  const loop = dialog.getByRole("switch", { name: "Loop-friendly ending" });
  await loop.click();
  await expect(loop).toBeChecked();
  await expect(dialog.getByLabel("Cost estimate")).not.toHaveText(
    "Estimating the cost…",
  );
  await loop.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: fileURLToPath(
      new URL("../.agent/screenshots/TASK-233-1.png", import.meta.url),
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
  const plan = (await (
    await request.get(`/api/proedit/clips/${variants.at(-1)!.id}/plan`)
  ).json()) as {
    items: { kind: string; t_end: number; params: { type?: string } }[];
  };
  const loops = plan.items.filter(
    (item) => item.kind === "transition" && item.params.type === "loop",
  );
  expect(loops).toHaveLength(1);
  expect(Math.max(...plan.items.map((item) => item.t_end))).toBe(
    loops[0].t_end,
  );
  expect(errors).toEqual([]);
});
