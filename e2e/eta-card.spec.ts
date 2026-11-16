import { expect, test, type Route } from "@playwright/test";
import { fileURLToPath } from "node:url";

test.use({ viewport: { width: 1280, height: 720 } });

const THUMB = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3b82f6"/><stop offset="1" stop-color="#27272a"/></linearGradient></defs><rect width="640" height="360" fill="url(#g)"/></svg>`;

function project(id: number, title: string, status: string, extra = {}) {
  return {
    id,
    source_url: "https://youtu.be/a",
    source_path: "",
    title,
    duration: 1200,
    thumbnail_path: "/work/thumb.jpg",
    settings: {},
    status,
    created_at: "2026-11-02T10:00:00",
    source_rights: null,
    credit_line: "",
    campaign_id: null,
    source_published_at: null,
    result_set: 1,
    overall_progress: 0,
    eta_seconds: null,
    opened_at: "2026-11-02T10:30:00",
    rights_set: false,
    fresh_upload: false,
    ...extra,
  };
}

function fulfil(route: Route, body: unknown) {
  return route.fulfill({ json: body });
}

test("a running project card shows its percent and ETA in a progress pill", async ({
  page,
}) => {
  const projects = [
    project(3, "Podcast episode 12", "running", {
      overall_progress: 0.48,
      eta_seconds: 300,
    }),
    project(2, "Interview", "done", { opened_at: null }),
    project(1, "Old talk", "done"),
  ];
  await page.route("**/api/projects", (route) => fulfil(route, projects));
  await page.route("**/api/projects/*/clips", (route) => fulfil(route, []));
  await page.route("**/api/projects/3/jobs", (route) =>
    fulfil(route, [
      {
        id: 7,
        project_id: 3,
        clip_id: null,
        kind: "process",
        step: "transcribe",
        progress: 0.4,
        status: "running",
        error: null,
        log_path: "",
        priority: 0,
        attempts: 1,
        overall_progress: 0.48,
        eta_seconds: 300,
      },
    ]),
  );
  await page.route(/\/media\/\d+\/thumbnail/, (route) =>
    route.fulfill({ contentType: "image/svg+xml", body: THUMB }),
  );

  await page.goto("/projects");

  const pill = page.getByRole("progressbar", {
    name: "Podcast episode 12 progress",
  });
  await expect(pill).toHaveText("48% (ETA 5m)");
  await expect(pill).toHaveAttribute("aria-valuenow", "48");
  await expect(
    page.getByRole("article", { name: "Interview" }).getByTestId("new-badge"),
  ).toHaveText("New");
  await expect(
    page.getByRole("article", { name: "Old talk" }).getByTestId("new-badge"),
  ).toHaveCount(0);

  await expect
    .poll(() =>
      page
        .locator("article img")
        .first()
        .evaluate((img: HTMLImageElement) => img.naturalWidth),
    )
    .toBeGreaterThan(0);
  await page.screenshot({
    path: fileURLToPath(
      new URL("../.agent/screenshots/steering-eta-card.png", import.meta.url),
    ),
  });
});
