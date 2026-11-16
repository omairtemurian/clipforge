import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import { Toaster } from "@/components/Toaster";
import { AppRoutes } from "@/routes";
import { mockEventSource } from "@/testing/fakeEventSource";
import {
  callsTo,
  job,
  json,
  mockRoutes,
  project,
  type Handler,
} from "@/testing/mockApi";
import { clearToasts } from "@/lib/toast";

const DONE = project({ id: 1, title: "First talk" });
const RUNNING = project({ id: 2, title: "Late set", status: "running" });
const QUEUED = project({ id: 3, title: "Queued show", status: "queued" });

function renderAt(path: string) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
}

/** The API of the page with the three projects, newest first. */
function routes(extra: Record<string, Handler> = {}) {
  return mockRoutes({
    "GET /api/projects": () => json([QUEUED, RUNNING, DONE]),
    "GET /api/projects/1/clips": () => json([{}, {}]),
    "GET /api/projects/2/jobs": () =>
      json([
        job({
          id: 8,
          project_id: 2,
          status: "running",
          step: "transcribe",
          progress: 0.5,
          overall_progress: 0.48,
          eta_seconds: 300,
        }),
      ]),
    "GET /api/projects/3/jobs": () => json([job({ project_id: 3 })]),
    ...extra,
  });
}

beforeEach(() => {
  mockEventSource();
});

afterEach(() => {
  vi.unstubAllGlobals();
  act(() => clearToasts());
});

describe("Projects page", () => {
  it("lists every project newest first with status, step and progress", async () => {
    routes();
    renderAt("/projects");

    const cards = await screen.findAllByRole("article");
    expect(cards.map((card) => card.getAttribute("aria-label"))).toEqual([
      "Queued show",
      "Late set",
      "First talk",
    ]);
    expect(cards[2]).toHaveTextContent("Ready");
    expect(
      await within(cards[2]).findByText(/2 clips · 2026\.10\.30/),
    ).toBeVisible();
    expect(within(cards[2]).queryByRole("progressbar")).toBeNull();

    const running = within(cards[1]);
    expect(cards[1]).toHaveTextContent("Processing");
    const bar = await running.findByRole("progressbar", {
      name: "Late set progress",
    });
    await waitFor(() => expect(bar).toHaveAttribute("aria-valuenow", "48"));
    expect(bar).toHaveTextContent("48% (ETA 5m)");
    expect(running.getByText("Transcribe")).toBeVisible();
    expect(within(cards[0]).getByText("Waiting in the queue")).toBeVisible();
    expect(within(cards[0]).queryByRole("progressbar")).toBeNull();
  });

  it("badges a finished project New until it is opened", async () => {
    const user = userEvent.setup();
    const fresh = { ...DONE, id: 4, title: "Fresh", opened_at: null };
    let opened = false;
    const fetchMock = routes({
      "GET /api/projects": () =>
        json([{ ...fresh, opened_at: opened ? DONE.opened_at : null }, DONE]),
      "GET /api/projects/4": () => json(fresh),
      "GET /api/projects/4/clips": () => json([]),
      "POST /api/projects/4/open": () => {
        opened = true;
        return json({ ...fresh, opened_at: DONE.opened_at });
      },
    });
    renderAt("/projects");

    const cards = await screen.findAllByRole("article");
    expect(within(cards[0]).getByTestId("new-badge")).toHaveTextContent("New");
    expect(within(cards[1]).queryByTestId("new-badge")).toBeNull();

    await user.click(
      within(cards[0]).getByRole("link", { name: "Open Fresh" }),
    );

    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", "/api/projects/4/open")).toHaveLength(
        1,
      ),
    );
  });

  it("shows the number of projects in progress on the sidebar link", async () => {
    routes();
    renderAt("/projects");

    const link = await screen.findByRole("link", {
      name: "Projects, 2 in progress",
    });
    expect(within(link).getByTestId("nav-badge")).toHaveTextContent("2");
  });

  it("opens the processing view from a running card", async () => {
    const user = userEvent.setup();
    routes({ "GET /api/projects/2": () => json(RUNNING) });
    renderAt("/projects");

    await user.click(
      await screen.findByRole("link", { name: "Open Late set" }),
    );

    expect(
      await screen.findByRole("progressbar", { name: "Overall progress" }),
    ).toBeVisible();
    expect(screen.getByRole("heading", { name: "Late set" })).toBeVisible();
  });

  it("renames a project from its kebab menu", async () => {
    const user = userEvent.setup();
    const fetchMock = routes({
      "PATCH /api/projects/1": () => json({ ...DONE, title: "Best of" }),
    });
    renderAt("/projects");

    await user.click(
      await screen.findByRole("button", { name: "Actions for First talk" }),
    );
    await user.click(await screen.findByRole("menuitem", { name: "Rename" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Rename project",
    });
    const field = within(dialog).getByLabelText("Title");
    await user.clear(field);
    expect(within(dialog).getByRole("button", { name: "Save" })).toBeDisabled();
    await user.type(field, "  Best of ");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    const [patch] = callsTo(fetchMock, "PATCH", "/api/projects/1");
    expect(JSON.parse(patch[1]?.body as string)).toEqual({ title: "Best of" });
  });

  it("deletes a project after confirming, but not a running one", async () => {
    const user = userEvent.setup();
    const fetchMock = routes({
      "DELETE /api/projects/1": () => new Response(null, { status: 204 }),
    });
    renderAt("/projects");

    await user.click(
      await screen.findByRole("button", { name: "Actions for Late set" }),
    );
    expect(
      await screen.findByRole("menuitem", { name: "Delete" }),
    ).toHaveAttribute("aria-disabled", "true");
    await user.keyboard("{Escape}");

    await user.click(
      screen.getByRole("button", { name: "Actions for First talk" }),
    );
    await user.click(await screen.findByRole("menuitem", { name: "Delete" }));
    const confirm = await screen.findByRole("alertdialog", {
      name: "Delete this project?",
    });
    expect(callsTo(fetchMock, "DELETE", "/api/projects/1")).toEqual([]);
    await user.click(within(confirm).getByRole("button", { name: "Delete" }));

    await waitFor(() =>
      expect(callsTo(fetchMock, "DELETE", "/api/projects/1")).toHaveLength(1),
    );
    expect(await screen.findByText("Project deleted.")).toBeVisible();
  });

  it("narrows the projects by the search query", async () => {
    routes();
    renderAt("/projects?q=late");

    expect(
      await screen.findByRole("article", { name: "Late set" }),
    ).toBeVisible();
    expect(screen.getAllByRole("article")).toHaveLength(1);
  });

  it("says when no project matches the search", async () => {
    routes();
    renderAt("/projects?q=nothing");

    expect(
      await screen.findByText("No project matches “nothing”."),
    ).toBeVisible();
  });

  it("narrows the projects by their status", async () => {
    const user = userEvent.setup();
    const FAILED = project({ id: 4, title: "Broken", status: "failed" });
    const ARCHIVED = project({
      id: 5,
      title: "Old show",
      archived_at: "2026-11-01T10:00:00",
    });
    routes({
      "GET /api/projects": () =>
        json([QUEUED, RUNNING, DONE, FAILED, ARCHIVED]),
      "GET /api/projects/5/clips": () => json([]),
    });
    renderAt("/projects");
    const names = () =>
      screen
        .getAllByRole("article")
        .map((card) => card.getAttribute("aria-label"));
    const status = await screen.findByRole("radiogroup", { name: "Status" });

    await screen.findAllByRole("article");
    expect(names()).toHaveLength(5);
    await user.click(within(status).getByRole("radio", { name: "Processing" }));
    expect(names()).toEqual(["Queued show", "Late set"]);
    await user.click(within(status).getByRole("radio", { name: "Ready" }));
    expect(names()).toEqual(["First talk"]);
    await user.click(within(status).getByRole("radio", { name: "Failed" }));
    expect(names()).toEqual(["Broken"]);
    await user.click(within(status).getByRole("radio", { name: "Archived" }));
    expect(names()).toEqual(["Old show"]);
    expect(screen.getByRole("article")).toHaveTextContent("Archived");
  });

  it("says when no project has the status", async () => {
    routes();
    renderAt("/projects?status=failed");

    expect(await screen.findByText("No failed projects.")).toBeVisible();
  });

  it("processes a failed project again from its menu", async () => {
    const user = userEvent.setup();
    const FAILED = project({ id: 4, title: "Broken", status: "failed" });
    const fetchMock = routes({
      "GET /api/projects": () => json([FAILED, DONE]),
      "POST /api/projects/4/reprocess": () =>
        json(job({ project_id: 4, status: "queued" }), 202),
    });
    renderAt("/projects");

    await user.click(
      await screen.findByRole("button", { name: "Actions for First talk" }),
    );
    expect(
      screen.queryByRole("menuitem", { name: "Process again" }),
    ).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.click(
      screen.getByRole("button", { name: "Actions for Broken" }),
    );
    await user.click(
      await screen.findByRole("menuitem", { name: "Process again" }),
    );

    await waitFor(() =>
      expect(
        callsTo(fetchMock, "POST", "/api/projects/4/reprocess"),
      ).toHaveLength(1),
    );
    expect(
      await screen.findByText("Processing the video again."),
    ).toBeVisible();
  });

  it("shows the empty state without projects", async () => {
    mockRoutes({ "GET /api/projects": () => json([]) });
    renderAt("/projects");

    expect(await screen.findByText("No projects yet")).toBeVisible();
    expect(screen.queryByTestId("nav-badge")).toBeNull();
  });
});
