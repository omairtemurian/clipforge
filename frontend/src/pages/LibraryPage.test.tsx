import { QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { SearchHit } from "@/api/types";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import { LibraryPage } from "@/pages/LibraryPage";
import {
  callsTo,
  clip,
  job,
  json,
  mockRoutes,
  project,
  type Handler,
} from "@/testing/mockApi";

const SEARCH = "/api/search?q=funny&limit=50";

function hit(overrides: Partial<SearchHit> = {}): SearchHit {
  return {
    project_id: 1,
    project_title: "First talk",
    segment_id: 10,
    start: 65,
    segment_start: 64,
    end: 70,
    text: "that was a funny bit",
    highlights: [{ start: 11, end: 16 }],
    rank: -2,
    ...overrides,
  };
}

const HITS = [
  hit(),
  hit({ project_id: 2, project_title: "Old show", segment_id: 4, start: 5 }),
  hit({ segment_id: 11, start: 125, text: "funny again" }),
];

function Where() {
  const location = useLocation();
  return <p data-testid="where">{location.pathname + location.search}</p>;
}

function renderAt(path: string) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/library" element={<LibraryPage />} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
}

function routes(extra: Record<string, Handler> = {}) {
  return mockRoutes({
    "GET /api/projects": () =>
      json([
        project({ id: 1, title: "First talk" }),
        project({
          id: 2,
          title: "Old show",
          archived_at: "2026-11-01T10:00:00",
        }),
      ]),
    [`GET ${SEARCH}`]: () => json(HITS),
    "GET /api/collections": () => json([]),
    ...extra,
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  act(() => clearToasts());
});

describe("Library page", () => {
  it("asks for a search before searching", () => {
    const fetchMock = routes();
    renderAt("/library");

    expect(screen.getByText("Search your videos")).toBeVisible();
    expect(
      fetchMock.mock.calls.filter(([url]) =>
        String(url).startsWith("/api/search"),
      ),
    ).toEqual([]);
  });

  it("searches on submit and marks the matched words", async () => {
    const user = userEvent.setup();
    routes();
    renderAt("/library");

    await user.type(
      screen.getByRole("searchbox", { name: "Search transcripts" }),
      "funny{Enter}",
    );

    const list = await screen.findByRole("list", { name: "Moments found" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    expect(
      within(list).getAllByText("funny", { selector: "mark" }),
    ).toHaveLength(2);
    expect(screen.getByText("3 moments found")).toBeVisible();
  });

  it("searches one project", async () => {
    const user = userEvent.setup();
    const fetchMock = routes({
      "GET /api/search?q=funny&limit=50&project_id=1": () => json([hit()]),
    });
    renderAt("/library?q=funny");

    await screen.findByRole("option", { name: "First talk" });
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Project" }),
      "1",
    );

    await waitFor(() =>
      expect(
        callsTo(fetchMock, "GET", "/api/search?q=funny&limit=50&project_id=1"),
      ).toHaveLength(1),
    );
    expect(await screen.findByText("1 moment found")).toBeVisible();
  });

  it("plays a moment from its start in the preview", async () => {
    const user = userEvent.setup();
    routes();
    renderAt("/library?q=funny");

    await user.click(
      await screen.findByRole("button", { name: "Play First talk at 02:05" }),
    );

    const video = screen.getByLabelText<HTMLVideoElement>(
      "Source video of First talk",
    );
    expect(video).toHaveAttribute("src", "/api/media/1/source");
    fireEvent(video, new Event("loadedmetadata"));
    expect(video.currentTime).toBe(125);
    expect(screen.getByText("First talk · from 02:05")).toBeVisible();
  });

  it("makes a clip of a moment and renders it", async () => {
    const user = userEvent.setup();
    const fetchMock = routes({
      "POST /api/search/clips": () => json(clip({ id: 31 }), 201),
      "POST /api/clips/31/render": () => json(job({ id: 5, clip_id: 31 }), 202),
    });
    renderAt("/library?q=funny");

    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Clip length" }),
      "60",
    );
    await user.click(
      await screen.findByRole("button", {
        name: "Make clip of First talk at 01:05",
      }),
    );

    const open = await screen.findByRole("link", { name: "Open clip" });
    expect(open).toHaveAttribute("href", "/clips/31");
    const [[, init]] = callsTo(fetchMock, "POST", "/api/search/clips");
    expect(JSON.parse(String(init?.body))).toEqual({
      project_id: 1,
      at: 65,
      length: 60,
    });
    expect(callsTo(fetchMock, "POST", "/api/clips/31/render")).toHaveLength(1);
  });

  it("keeps the moments of an archived project from being clipped", async () => {
    routes();
    renderAt("/library?q=funny");

    expect(
      await screen.findByRole("button", {
        name: "Make clip of Old show at 00:05",
      }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Play Old show at 00:05" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("checkbox", { name: "Select Old show at 00:05" }),
    ).toBeDisabled();
  });

  it("exports the selected moments as clips to a new collection", async () => {
    const user = userEvent.setup();
    let next = 40;
    const fetchMock = routes({
      "POST /api/collections": () =>
        json({ id: 9, name: "Moments: funny", items: [] }, 201),
      "POST /api/search/clips": () => json(clip({ id: next++ }), 201),
      "POST /api/clips/40/render": () => json(job(), 202),
      "POST /api/clips/41/render": () => json(job(), 202),
      "POST /api/collections/9/items": () => json({ id: 9, items: [] }),
    });
    renderAt("/library?q=funny");

    await user.click(await screen.findByRole("button", { name: "Select all" }));
    expect(screen.getByText(/2 selected/)).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "Export to collection" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Add to collection",
    });
    expect(within(dialog).getByRole("textbox", { name: "Name" })).toHaveValue(
      "Moments: funny",
    );
    await user.click(within(dialog).getByRole("button", { name: "Add" }));

    await waitFor(() =>
      expect(screen.getByTestId("where")).toHaveTextContent(
        "/collections?id=9",
      ),
    );
    const [[, init]] = callsTo(fetchMock, "POST", "/api/collections/9/items");
    expect(JSON.parse(String(init?.body))).toEqual({ clip_ids: [40, 41] });
    expect(
      await screen.findByText("Added 2 moments to the collection."),
    ).toBeVisible();
  });
});
