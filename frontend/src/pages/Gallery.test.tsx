import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { Clip, Job } from "@/api/types";
import {
  callsTo,
  clip,
  json,
  mockRoutes,
  project,
  scored,
} from "@/testing/mockApi";
import { Gallery } from "./Gallery";

function job(overrides: Partial<Job>): Job {
  return {
    id: 5,
    project_id: 1,
    clip_id: null,
    kind: "process",
    step: "",
    progress: 1,
    status: "done",
    error: null,
    log_path: "",
    priority: 0,
    attempts: 0,
    overall_progress: 1,
    eta_seconds: null,
    ...overrides,
  };
}

const CLIPS: Clip[] = [
  scored(1, 95, "Pizza night"),
  { ...scored(2, 70, "Yoga class"), status: "rendered" },
  scored(3, 40, "Smart fridge"),
];

function renderGallery() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <Gallery project={project({ id: 1 })} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function api(clips: Clip[] = CLIPS, jobs: Job[] = []) {
  let current = clips;
  const fetchMock = mockRoutes({
    "GET /api/campaigns": () => json([]),
    "GET /api/collections": () =>
      json([
        {
          id: 9,
          name: "Best bits",
          description: "",
          created_at: "2026-11-01T10:00:00",
          updated_at: "2026-11-01T10:00:00",
          clip_count: 0,
        },
      ]),
    "POST /api/collections/9/items": () => json({ id: 9, items: [] }),
    "GET /api/projects/1/clips": () => json(current),
    "GET /api/projects/1/jobs": () => json(jobs),
    "POST /api/clips/1/render": () => json(job({ kind: "render", clip_id: 1 })),
    "POST /api/clips/3/render": () => json(job({ kind: "render", clip_id: 3 })),
    "DELETE /api/clips/1": () => {
      current = current.filter((item) => item.id !== 1);
      return new Response(null, { status: 204 });
    },
  });
  return fetchMock;
}

function titles(): string[] {
  return screen
    .getAllByRole("heading", { level: 3 })
    .map((h) => h.textContent ?? "");
}

beforeEach(() => {
  vi.stubGlobal(
    "confirm",
    vi.fn(() => true),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Gallery", () => {
  it("lists the clips best first with the count", async () => {
    api();
    renderGallery();

    expect(await screen.findByText("Pizza night")).toBeInTheDocument();
    expect(titles()).toEqual(["Pizza night", "Yoga class", "Smart fridge"]);
    expect(
      screen.getByRole("heading", { name: "Clips (3)" }),
    ).toBeInTheDocument();
    const card = screen.getByRole("article", { name: "Pizza night" });
    expect(
      within(card).getByRole("button", { name: /Score 95/ }),
    ).toBeInTheDocument();
    expect(within(card).getByLabelText("Duration")).toHaveTextContent("00:30");
    expect(within(card).getByText("Fill")).toBeInTheDocument();
  });

  it("searches, sorts and filters by the minimum score", async () => {
    api();
    renderGallery();
    await screen.findByText("Pizza night");

    await userEvent.type(screen.getByLabelText("Search clips"), "yoga");
    expect(titles()).toEqual(["Yoga class"]);

    await userEvent.clear(screen.getByLabelText("Search clips"));
    await userEvent.type(screen.getByLabelText("Search clips"), "zzz");
    expect(screen.getByText("No clips match")).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Search clips"));

    const slider = screen.getByRole("slider", { name: "Min score" });
    slider.focus();
    await userEvent.keyboard("{End}");
    expect(screen.getByText("No clips match")).toBeInTheDocument();
    await userEvent.keyboard("{Home}");
    expect(titles()).toHaveLength(3);
    await userEvent.keyboard(
      "{PageUp}{PageUp}{PageUp}{PageUp}{PageUp}{PageUp}{PageUp}",
    );
    expect(titles()).toEqual(["Pizza night", "Yoga class"]);

    await userEvent.selectOptions(screen.getByLabelText("Sort by"), "duration");
    expect(titles()).toEqual(["Pizza night", "Yoga class"]);
  });

  it("adds the clips shown to an existing collection", async () => {
    const fetchMock = api();
    renderGallery();
    await screen.findByText("Pizza night");
    await userEvent.type(screen.getByLabelText("Search clips"), "yoga");

    await userEvent.click(
      screen.getByRole("button", { name: "Add to collection" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Add to collection",
    });
    await within(dialog).findByRole("option", { name: "Best bits" });
    await userEvent.selectOptions(
      within(dialog).getByRole("combobox", { name: "Collection" }),
      "9",
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Add" }));

    await waitFor(() =>
      expect(
        callsTo(fetchMock, "POST", "/api/collections/9/items"),
      ).toHaveLength(1),
    );
    const [[, init]] = callsTo(fetchMock, "POST", "/api/collections/9/items");
    expect(JSON.parse(String(init?.body))).toEqual({ clip_ids: [2] });
  });

  it("plays the preview while a card is hovered", async () => {
    api();
    renderGallery();
    const card = await screen.findByRole("article", { name: "Pizza night" });
    expect(within(card).queryByLabelText(/Preview of/)).not.toBeInTheDocument();

    await userEvent.hover(within(card).getByLabelText("Duration"));

    const video = within(card).getByLabelText("Preview of Pizza night");
    expect(video).toHaveAttribute("src", "/api/clips/1/preview");
    expect(video).toHaveProperty("muted", true);
    await userEvent.unhover(within(card).getByLabelText("Duration"));
    expect(within(card).queryByLabelText(/Preview of/)).not.toBeInTheDocument();
  });

  it("downloads a rendered clip and renders a candidate first", async () => {
    const fetchMock = api();
    renderGallery();
    const rendered = await screen.findByRole("article", { name: "Yoga class" });
    expect(
      within(rendered).getByRole("link", { name: "Download clip" }),
    ).toHaveAttribute("href", "/api/clips/2/download");

    const candidate = screen.getByRole("article", { name: "Pizza night" });
    await userEvent.click(
      within(candidate).getByRole("button", { name: "Render clip" }),
    );

    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", "/api/clips/1/render")).toHaveLength(1),
    );
  });

  it("shows a clip that is rendering as busy", async () => {
    api(CLIPS, [job({ id: 8, kind: "render", clip_id: 1, status: "running" })]);
    renderGallery();

    const card = await screen.findByRole("article", { name: "Pizza night" });
    await waitFor(() =>
      expect(
        within(card).getByRole("button", { name: "Rendering" }),
      ).toBeDisabled(),
    );
    expect(screen.getByRole("button", { name: "Rendering…" })).toBeDisabled();
  });

  it("links Download all to the zip once every clip is rendered", async () => {
    api([{ ...scored(2, 70, "Yoga class"), status: "rendered" }]);
    renderGallery();

    const link = await screen.findByRole("link", { name: /Download all/ });
    expect(link).toHaveAttribute("href", "/api/projects/1/download.zip");
  });

  it("renders the clips that are not rendered with Download all", async () => {
    const fetchMock = api();
    renderGallery();

    await userEvent.click(
      await screen.findByRole("button", { name: "Download all" }),
    );

    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", "/api/clips/1/render")).toHaveLength(1),
    );
    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", "/api/clips/3/render")).toHaveLength(1),
    );
    expect(callsTo(fetchMock, "POST", "/api/clips/2/render")).toHaveLength(0);
  });

  it("removes a clip after confirming", async () => {
    const fetchMock = api();
    renderGallery();
    const card = await screen.findByRole("article", { name: "Pizza night" });

    await userEvent.click(
      within(card).getByRole("button", { name: "Remove clip" }),
    );

    await waitFor(() =>
      expect(screen.queryByText("Pizza night")).not.toBeInTheDocument(),
    );
    expect(callsTo(fetchMock, "DELETE", "/api/clips/1")).toHaveLength(1);
    expect(titles()).toEqual(["Yoga class", "Smart fridge"]);
  });

  it("keeps the clip when the removal is not confirmed", async () => {
    vi.stubGlobal(
      "confirm",
      vi.fn(() => false),
    );
    const fetchMock = api();
    renderGallery();
    const card = await screen.findByRole("article", { name: "Pizza night" });

    await userEvent.click(
      within(card).getByRole("button", { name: "Remove clip" }),
    );

    expect(callsTo(fetchMock, "DELETE", "/api/clips/1")).toHaveLength(0);
  });

  it("links Edit to the clip and says so when there are no clips", async () => {
    api([clip({ id: 4, title: "Solo" })]);
    const view = renderGallery();
    expect(
      await screen.findByRole("link", { name: "Edit clip" }),
    ).toHaveAttribute("href", "/clips/4");
    view.unmount();

    api([]);
    renderGallery();
    expect(await screen.findByText("No clips found")).toBeInTheDocument();
    expect(screen.queryByLabelText("Search clips")).not.toBeInTheDocument();
  });
});
