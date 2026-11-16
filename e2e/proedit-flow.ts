import {
  expect,
  type APIRequestContext,
  type Locator,
  type Page,
} from "@playwright/test";
import { fileURLToPath } from "node:url";

const SAMPLE = fileURLToPath(
  new URL("../backend/tests/fixtures/sample.mp4", import.meta.url),
);
export const PIPELINE_TIMEOUT = 180_000;
export const PRO_EDIT_TIMEOUT = 180_000;
// A 1x1 PNG: the API only checks the image's magic bytes.
const PROOF = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

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

/** Make a Phonk Edit variant of clip id and wait until it is rendered;
 * returns the variant's id. */
async function makeVariant(request: APIRequestContext, id: number) {
  const started = await request.post(`/api/proedit/clips/${id}/runs`, {
    data: { preset: "phonk_edit", use_critic: false },
  });
  expect(started.status()).toBe(202);
  const { clip, run } = (await started.json()) as {
    clip: { id: number };
    run: { id: number };
  };
  await expect
    .poll(
      async () =>
        (await (await request.get(`/api/proedit/runs/${run.id}`)).json())
          .status,
      { timeout: PRO_EDIT_TIMEOUT, intervals: [1000] },
    )
    .toBe("done");
  return clip.id;
}

/** Upload the sample video through the UI and wait for its clips;
 * returns the project and its first clip's ids. */
export async function uploadSample(page: Page, request: APIRequestContext) {
  await page.goto("/");
  await page.getByLabel("Upload a video file").setInputFiles(SAMPLE);
  const settings = page.getByRole("dialog", { name: "Clip settings" });
  await settings.getByLabel("Source rights").selectOption("own");
  await settings.getByRole("button", { name: "Get clips" }).click();
  await expect(page).toHaveURL(/\/projects\/\d+$/);
  const projectId = page.url().split("/").pop()!;
  await waitUntilEnded(request, projectId);
  const clips = (await (
    await request.get(`/api/projects/${projectId}/clips`)
  ).json()) as { id: number }[];
  return { projectId, originalId: clips[0].id };
}

/** Upload the sample video through the UI, wait for its clips and make a
 * Pro Edit variant of the first; returns the project, original and variant
 * ids. */
export async function uploadAndMakeVariant(
  page: Page,
  request: APIRequestContext,
) {
  const { projectId, originalId } = await uploadSample(page, request);
  const variantId = await makeVariant(request, originalId);
  return { projectId, originalId, variantId };
}

/** Collect the page's console errors and uncaught exceptions. */
export function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

/** A campaign that allows heavy edits up to Pro and whose approved clips
 * are posted to a test YouTube account in its autopilot's slots (autopilot
 * off); returns its and the account's ids. */
export async function postingCampaign(request: APIRequestContext) {
  const account = await request.post("/api/testmode/accounts/youtube", {
    params: { name: "Pro Edit Channel" },
  });
  expect(account.status()).toBe(201);
  const accountId = ((await account.json()) as { id: number }).id;
  const created = await request.post("/api/campaigns", {
    data: {
      name: "Skull clips",
      creator_name: "Afro",
      allowed_platforms: ["youtube"],
      rate_per_1k_usd: 1.5,
      permission_source_url: "https://example.com/permission",
      allow_heavy_edits: "true",
    },
  });
  expect(created.status()).toBe(201);
  const campaignId = ((await created.json()) as { id: number }).id;
  await request.post(`/api/campaigns/${campaignId}/permission-screenshot`, {
    multipart: {
      file: { name: "proof.png", mimeType: "image/png", buffer: PROOF },
    },
  });
  const autopilot = await request.put(
    `/api/campaigns/${campaignId}/autopilot`,
    {
      data: {
        enabled: false,
        account_ids: [accountId],
        proedit_max_intensity: "pro",
        slots: { timezone: "Europe/Zurich", times: ["09:00", "18:00"] },
      },
    },
  );
  expect(autopilot.status()).toBe(200);
  return { campaignId, accountId };
}

/** Open the gallery's first card's Pro Edit dialog and run preset at
 * intensity (the slider's index), with the style recipe recipe if given;
 * follow the progress until the variant is ready. */
export async function runProEdit(
  page: Page,
  preset: string,
  intensity: { index: number; label: string },
  recipe?: string,
) {
  await page
    .getByRole("article")
    .first()
    .getByRole("button", { name: "Pro Edit" })
    .click();
  const dialog = page.getByRole("dialog", { name: "Pro Edit" });
  await dialog.getByText(preset, { exact: true }).click();
  await expect(dialog.getByRole("radio", { name: preset })).toBeChecked();
  const slider = dialog.getByRole("slider", { name: /^Intensity/ });
  await slider.fill(String(intensity.index));
  await expect(slider).toHaveAttribute("aria-valuetext", intensity.label);
  if (recipe !== undefined) {
    await dialog.getByLabel("Style recipe").selectOption({ label: recipe });
  }
  await expect(dialog.getByLabel("Cost estimate")).not.toHaveText(
    "Estimating the cost…",
  );
  await dialog.getByRole("button", { name: "Run Pro Edit" }).click();
  return dialog;
}

/** The middle of lane's item with the most free room after it (to the
 * next item or the lane's end) and that room in pixels. */
export async function roomiestItem(lane: Locator) {
  const end = (await lane.boundingBox())!;
  const boxes = (
    await Promise.all(
      (await lane.getByTestId("edl-item").all()).map((i) => i.boundingBox()),
    )
  )
    .filter((box) => box !== null)
    .sort((a, b) => a.x - b.x);
  const spots = boxes.map((box, n) => ({
    x: box.x + box.width / 2,
    y: box.y + box.height / 2,
    room: (boxes[n + 1]?.x ?? end.x + end.width) - (box.x + box.width),
  }));
  return spots.reduce((best, spot) => (spot.room > best.room ? spot : best));
}
