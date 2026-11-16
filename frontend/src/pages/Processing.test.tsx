import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { createQueryClient } from "@/api/queryClient";
import { FakeEventSource, mockEventSource } from "@/testing/fakeEventSource";
import { job, json, mockRoutes, project, scored } from "@/testing/mockApi";
import { ProjectPage } from "./ProjectPage";

function renderProject() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={["/projects/1"]}>
        <Routes>
          <Route path="/projects/:projectId" element={<ProjectPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function routes(status: "queued" | "running" | "done" | "failed") {
  let current = status;
  mockRoutes({
    "GET /api/projects/1": () => json(project({ status: current })),
    "GET /api/projects/1/clips": () => json([scored(1, 90, "Pizza night")]),
    "GET /api/projects/1/jobs": () =>
      json([job({ kind: "render", id: 9 }), job()]),
  });
  return (next: typeof status) => {
    current = next;
  };
}

async function source(): Promise<FakeEventSource> {
  await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
  return FakeEventSource.instances[0];
}

beforeEach(() => {
  mockEventSource();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Processing", () => {
  it("follows the process job's events of the project", async () => {
    routes("running");
    renderProject();
    const events = await source();
    expect(events.url).toBe("/api/jobs/7/events");

    act(() =>
      events.emit({
        step: "transcribe",
        progress: 0.5,
        status: "running",
        message: "Running transcribe.",
      }),
    );

    const steps = within(
      screen.getByRole("list", { name: "Processing steps" }),
    );
    const items = steps.getAllByRole("listitem");
    expect(items.map((item) => item.dataset.state)).toEqual([
      "done",
      "running",
      "pending",
      "pending",
      "pending",
      "pending",
      "pending",
    ]);
    expect(items[1]).toHaveTextContent("In progress 50%");
    const bar = screen.getByRole("progressbar", { name: "Overall progress" });
    expect(bar).toHaveAttribute("aria-valuenow", "21");
    expect(screen.getByLabelText("Elapsed time")).toBeInTheDocument();
  });

  it("shows the overall percent and ETA the server sends", async () => {
    routes("running");
    renderProject();
    const events = await source();
    const emit = (eta: number | null) =>
      act(() =>
        events.emit({
          step: "transcribe",
          progress: 0.5,
          status: "running",
          message: "Running transcribe.",
          overall_progress: 0.48,
          eta_seconds: eta,
        }),
      );

    emit(null);
    const bar = screen.getByRole("progressbar", { name: "Overall progress" });
    expect(bar).toHaveAttribute("aria-valuenow", "48");
    expect(screen.getByText("48% · ETA …")).toBeVisible();

    emit(4200);
    expect(screen.getByText("48% · ETA 1h 10m")).toBeVisible();
  });

  it("shows the Converting video sub-step while ingest converts", async () => {
    routes("running");
    renderProject();
    const events = await source();
    const emit = (progress: number) =>
      act(() =>
        events.emit({
          step: "ingest",
          progress,
          status: "running",
          message: "Running ingest.",
        }),
      );

    emit(0.3);
    expect(screen.queryByLabelText("Current sub-step")).toBeNull();
    emit(0.7);
    const download = screen.getAllByRole("listitem")[0];
    expect(
      within(download).getByLabelText("Current sub-step"),
    ).toHaveTextContent("Converting video 49%");
    expect(download).toHaveTextContent("In progress 70%");
    emit(0.95);
    expect(screen.queryByLabelText("Current sub-step")).toBeNull();
  });

  it("follows a reprompt job when it is the newest", async () => {
    mockRoutes({
      "GET /api/projects/1": () => json(project({ status: "queued" })),
      "GET /api/projects/1/jobs": () =>
        json([job({ kind: "reprompt", id: 11 }), job()]),
    });
    renderProject();

    expect((await source()).url).toBe("/api/jobs/11/events");
  });

  it("resumes at the current step when the page is opened again", async () => {
    routes("running");
    renderProject();
    const events = await source();
    act(() =>
      events.emit({
        step: "score",
        progress: 0,
        status: "running",
        message: "Running score.",
      }),
    );
    const items = screen.getAllByRole("listitem");
    expect(items.map((item) => item.dataset.state)).toEqual([
      "done",
      "done",
      "done",
      "done",
      "running",
      "pending",
      "pending",
    ]);
  });

  it("shows the log lines in the drawer, one per listed step", async () => {
    routes("running");
    renderProject();
    const events = await source();
    act(() => {
      events.emit({
        step: "ingest",
        progress: 0.1,
        status: "running",
        message: "",
      });
      events.emit({
        step: "ingest",
        progress: 0.9,
        status: "running",
        message: "",
      });
      events.emit({
        step: "signals",
        progress: 0,
        status: "running",
        message: "",
      });
      events.emit({
        step: "enrich",
        progress: 0,
        status: "running",
        message: "",
      });
    });

    await userEvent.click(screen.getByRole("button", { name: /live log/i }));
    const lines = within(screen.getByRole("log")).getAllByText(/Started/);
    expect(lines.map((line) => line.textContent)).toEqual([
      expect.stringContaining("Started: Download."),
      expect.stringContaining("Started: Analyze audio."),
    ]);
  });

  it("shows the error of a failed job at the failed step", async () => {
    routes("running");
    renderProject();
    const events = await source();
    act(() =>
      events.emit({
        step: "ingest",
        progress: 0.3,
        status: "failed",
        message: "The video is private.",
      }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The video is private.",
    );
    expect(screen.getAllByRole("listitem")[0].dataset.state).toBe("failed");
    expect(events.closed).toBe(true);
    expect(screen.queryByLabelText("Elapsed time")).not.toBeInTheDocument();
  });

  it("closes the stream and shows the clips when the job is done", async () => {
    const setStatus = routes("running");
    renderProject();
    const events = await source();
    setStatus("done");
    act(() =>
      events.emit({
        step: "render",
        progress: 1,
        status: "done",
        message: "Done.",
      }),
    );
    expect(events.closed).toBe(true);
    expect(await screen.findByText("Pizza night")).toBeInTheDocument();
  });

  it("shows the clips of a done project without following a job", async () => {
    routes("done");
    renderProject();
    expect(await screen.findByText("Pizza night")).toBeInTheDocument();
    expect(FakeEventSource.instances).toHaveLength(0);
  });
});
