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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { createQueryClient } from "@/api/queryClient";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import {
  DEFAULTS,
  callsTo,
  json,
  mockApi,
  mockRoutes,
  project,
} from "@/testing/mockApi";
import { HomePage } from "./HomePage";
import { ProjectPage } from "./ProjectPage";

const CAPTIONS_CHIP = "Captions only (no clipping — whole video as one clip)";

const UPLOAD_ID = "c".repeat(32);
// sha256("data"), the bytes of the uploaded test file.
const DATA_SHA256 =
  "3a6eb0790f39ac87c94f3856b2dd2c5d110e6811602261a9a923d3bb23adc8b7";

function renderHome() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/projects/:projectId" element={<ProjectPage />} />
        </Routes>
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
}

/** The API of the panel: no projects yet, defaults, templates, no brands. */
function panelRoutes(extra: Parameters<typeof mockRoutes>[0] = {}) {
  return mockRoutes({
    "GET /api/projects": () => json([]),
    "GET /api/processing-defaults": () => json(DEFAULTS),
    "GET /api/caption-templates": () => json([]),
    "GET /api/brand-templates": () => json([]),
    ...extra,
  });
}

beforeEach(() => {
  vi.useRealTimers();
});

afterEach(() => {
  vi.unstubAllGlobals();
  act(() => clearToasts());
});

describe("Home tool chips", () => {
  it("shows the long-video tool as the pressed chip, next to Captions only", async () => {
    mockApi(() => json([]));
    renderHome();

    const chips = screen.getByRole("list", { name: "Tools" });
    expect(
      within(chips).getByRole("button", { name: "Long video to shorts" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      within(chips).getByRole("button", { name: CAPTIONS_CHIP }),
    ).toHaveAttribute("aria-pressed", "false");
  });
});

describe("Home recent projects", () => {
  it("shows skeletons while loading, then the grid", async () => {
    let release: (response: Response) => void = () => {};
    mockApi((url) =>
      url === "/api/projects"
        ? (new Promise<Response>((resolve) => (release = resolve)) as never)
        : json([]),
    );
    renderHome();

    expect(screen.getAllByTestId("project-skeleton")).toHaveLength(4);
    act(() => release(json([project({})])));

    expect(await screen.findByText("First talk")).toBeInTheDocument();
    expect(screen.queryByTestId("project-skeleton")).not.toBeInTheDocument();
  });

  it("renders a card with title, status, clip count and date", async () => {
    mockApi((url) => {
      if (url === "/api/projects/1/clips") return json([{}, {}, {}]);
      return json([
        project({}),
        project({ id: 2, title: "", status: "running", thumbnail_path: "" }),
      ]);
    });
    renderHome();

    const card = await screen.findByRole("article", { name: "First talk" });
    expect(card).toHaveTextContent("Ready");
    expect(await screen.findByText(/3 clips · 2026\.10\.30/)).toBeVisible();
    expect(card.querySelector("img")).toHaveAttribute(
      "src",
      "/api/media/1/thumbnail",
    );
    const waiting = screen.getByRole("article", { name: "https://youtu.be/a" });
    expect(waiting).toHaveTextContent("Processing");
    expect(waiting.querySelector("img")).toBeNull();
    expect(
      within(waiting).getByRole("progressbar", {
        name: "https://youtu.be/a progress",
      }),
    ).toBeVisible();
    expect(
      within(card).getByRole("link", { name: "Open First talk" }),
    ).toHaveAttribute("href", "/projects/1");
    expect(screen.getByRole("link", { name: "View all" })).toHaveAttribute(
      "href",
      "/projects",
    );
  });

  it("shows the empty state without projects", async () => {
    mockApi(() => json([]));
    renderHome();

    expect(await screen.findByText("No projects yet")).toBeVisible();
  });

  it("offers a retry when the projects cannot load", async () => {
    const user = userEvent.setup();
    let fail = true;
    mockApi(() =>
      fail ? json({ error: "boom", message: "Server broke" }, 400) : json([]),
    );
    renderHome();

    expect(
      await screen.findByText("Could not load your projects."),
    ).toBeVisible();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("No projects yet")).toBeVisible();
  });
});

describe("Home link input", () => {
  it("rejects a bad link without calling the API", async () => {
    const user = userEvent.setup();
    const fetchMock = mockApi(() => json([]));
    renderHome();
    await screen.findByText("No projects yet");

    await user.type(screen.getByLabelText("Video link"), "not a link");
    await user.click(screen.getByRole("button", { name: "Get clips" }));

    expect(screen.getByRole("alert")).toHaveTextContent("full video link");
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method)).toEqual([]);
  });

  it("opens the settings panel for a valid link, then creates the project and opens it", async () => {
    const user = userEvent.setup();
    const created = project({ id: 7, title: "", status: "queued" });
    const fetchMock = panelRoutes({
      "POST /api/sources/probe": () =>
        json({
          url: "https://youtu.be/a",
          title: "Late night set",
          duration: 754,
          thumbnail_url: "https://img.example/a.jpg",
        }),
      "POST /api/projects": () => json(created, 201),
      "GET /api/projects/7": () => json(created),
      "GET /api/projects/7/jobs": () => json([]),
    });
    renderHome();
    await screen.findByText("No projects yet");

    await user.type(screen.getByLabelText("Video link"), "youtu.be/a");
    await user.click(screen.getByRole("button", { name: "Get clips" }));

    const panel = await screen.findByRole("dialog", { name: "Clip settings" });
    expect(await within(panel).findByText("Late night set")).toBeVisible();
    expect(within(panel).getAllByText("12:34")).not.toHaveLength(0);
    expect(callsTo(fetchMock, "POST", "/api/projects")).toEqual([]);
    expect(screen.getByLabelText("Video link")).toHaveValue("");

    await user.selectOptions(
      within(panel).getByLabelText("Source rights"),
      "cc_by",
    );
    await user.type(within(panel).getByLabelText("Credit line"), "Ann, CC BY");
    await user.click(within(panel).getByRole("button", { name: "Get clips" }));

    expect(
      await screen.findByRole("heading", { name: "https://youtu.be/a" }),
    ).toBeVisible();
    expect(screen.getByRole("progressbar")).toBeVisible();
    const [post] = callsTo(fetchMock, "POST", "/api/projects");
    expect(JSON.parse(post[1]?.body as string)).toEqual({
      url: "https://youtu.be/a",
      settings: DEFAULTS,
      source_rights: "cc_by",
      credit_line: "Ann, CC BY",
    });
    expect(screen.getByText(/ClipForge is looking for clips/)).toBeVisible();
  });

  it("closes the panel without creating anything", async () => {
    const user = userEvent.setup();
    const fetchMock = panelRoutes({
      "POST /api/sources/probe": () =>
        json({ error: "probe_failed", message: "a playlist" }, 422),
    });
    renderHome();
    await screen.findByText("No projects yet");

    await user.type(screen.getByLabelText("Video link"), "https://youtu.be/a");
    await user.click(screen.getByRole("button", { name: "Get clips" }));
    await screen.findByRole("dialog", { name: "Clip settings" });
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog", { name: "Clip settings" })).toBeNull();
    expect(callsTo(fetchMock, "POST", "/api/projects")).toEqual([]);
  });
});

describe("Home file upload", () => {
  it("uploads a video picked with the Upload button, with its settings", async () => {
    const user = userEvent.setup();
    const session = { id: UPLOAD_ID, filename: "demo.mp4", size: 4, offset: 0 };
    let releaseChunk: () => void = () => {};
    const fetchMock = panelRoutes({
      "POST /api/uploads": () => json(session, 201),
      [`PATCH /api/uploads/${UPLOAD_ID}?offset=0`]: () =>
        new Promise<Response>((resolve) => {
          releaseChunk = () => resolve(json({ ...session, offset: 4 }));
        }),
      [`POST /api/uploads/${UPLOAD_ID}/complete`]: () =>
        json(project({ id: 3 }), 201),
      "GET /api/projects/3": () => json(project({ id: 3 })),
    });
    renderHome();
    await screen.findByText("No projects yet");

    const video = new File(["data"], "demo.mp4", { type: "video/mp4" });
    await user.upload(screen.getByLabelText("Upload a video file"), video);
    const panel = await screen.findByRole("dialog", { name: "Clip settings" });
    expect(within(panel).getByText("demo")).toBeVisible();
    const getClips = within(panel).getByRole("button", { name: "Get clips" });
    await waitFor(() => expect(getClips).toBeEnabled());
    await user.selectOptions(
      within(panel).getByLabelText("Source rights"),
      "own",
    );
    await user.click(getClips);

    expect(await within(panel).findByText("Uploading 0%")).toBeVisible();
    expect(
      within(panel).getByRole("progressbar", { name: "Upload progress" }),
    ).toHaveAttribute("aria-valuenow", "0");
    releaseChunk();
    expect(
      await screen.findByRole("heading", { name: "First talk" }),
    ).toBeVisible();
    const [chunk] = callsTo(
      fetchMock,
      "PATCH",
      `/api/uploads/${UPLOAD_ID}?offset=0`,
    );
    expect(new Headers(chunk[1]?.headers).get("X-Chunk-SHA256")).toBe(
      DATA_SHA256,
    );
    const [complete] = callsTo(
      fetchMock,
      "POST",
      `/api/uploads/${UPLOAD_ID}/complete`,
    );
    expect(JSON.parse(complete[1]?.body as string)).toEqual({
      settings: DEFAULTS,
      source_rights: "own",
      credit_line: "",
    });
  });

  it("shows the drop overlay and opens the panel for a dropped video", async () => {
    panelRoutes();
    renderHome();
    await screen.findByText("No projects yet");

    const video = new File(["data"], "drop.mov", { type: "video/quicktime" });
    const transfer = { types: ["Files"], files: [video] };
    fireEvent.dragEnter(window, { dataTransfer: transfer });
    expect(screen.getByText("Drop a video to get clips")).toBeVisible();
    fireEvent.drop(window, { dataTransfer: transfer });

    expect(screen.queryByText("Drop a video to get clips")).toBeNull();
    const panel = await screen.findByRole("dialog", { name: "Clip settings" });
    expect(within(panel).getByText("drop")).toBeVisible();
  });
  it("reports a dropped file that is not a video", async () => {
    const fetchMock = mockApi(() => json([]));
    renderHome();
    await screen.findByText("No projects yet");

    const text = new File(["x"], "notes.txt", { type: "text/plain" });
    fireEvent.drop(window, {
      dataTransfer: { types: ["Files"], files: [text] },
    });

    expect(await screen.findByText(/Drop a video file/)).toBeVisible();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method)).toEqual([]);
  });
});
