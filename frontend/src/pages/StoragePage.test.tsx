import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { ProjectStorage, StorageReport } from "@/api/types";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import { StoragePage } from "@/pages/StoragePage";
import { callsTo, json, mockRoutes, type Handler } from "@/testing/mockApi";

function usage(overrides: Partial<ProjectStorage>): ProjectStorage {
  return {
    project_id: 1,
    title: "First talk",
    status: "done",
    archived_at: null,
    source_bytes: 2_000_000_000,
    work_bytes: 500_000_000,
    output_bytes: 300_000_000,
    cleanable_bytes: 2_100_000_000,
    total_bytes: 2_800_000_000,
    ...overrides,
  };
}

const REPORT: StorageReport = {
  projects: [
    usage({}),
    usage({
      project_id: 2,
      title: "Live set",
      status: "running",
      total_bytes: 900_000_000,
    }),
  ],
  total_bytes: 3_700_000_000,
  free_bytes: 120_000_000_000,
  data_dir: "/home/me/clipforge/data",
};

function renderPage() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={["/settings/storage"]}>
        <StoragePage />
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
}

function routes(extra: Record<string, Handler> = {}) {
  return mockRoutes({ "GET /api/storage": () => json(REPORT), ...extra });
}

afterEach(() => {
  vi.unstubAllGlobals();
  act(() => clearToasts());
});

describe("Storage page", () => {
  it("shows the disk use of each project and the free space", async () => {
    routes();
    renderPage();

    expect(await screen.findByText("3.7 GB")).toBeVisible();
    expect(screen.getByText("120 GB")).toBeVisible();
    expect(screen.getByText("/home/me/clipforge/data")).toBeVisible();
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(within(rows[1]).getByText("2.8 GB")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Clean up Live set" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Archive Live set" }),
    ).toBeDisabled();
  });

  it("cleans up a project after a confirmation", async () => {
    const user = userEvent.setup();
    const fetchMock = routes({
      "POST /api/projects/1/cleanup": () =>
        json({ freed_bytes: 2_100_000_000, storage: usage({}) }),
    });
    renderPage();

    await user.click(
      await screen.findByRole("button", { name: "Clean up First talk" }),
    );
    const confirm = await screen.findByRole("alertdialog", {
      name: "Clean up this project?",
    });
    expect(confirm).toHaveTextContent("freeing about 2.1 GB");
    expect(callsTo(fetchMock, "POST", "/api/projects/1/cleanup")).toEqual([]);
    await user.click(within(confirm).getByRole("button", { name: "Clean up" }));

    await waitFor(() =>
      expect(
        callsTo(fetchMock, "POST", "/api/projects/1/cleanup"),
      ).toHaveLength(1),
    );
    expect(await screen.findByText("Cleaned up. 2.1 GB freed.")).toBeVisible();
  });

  it("archives a project after a warning", async () => {
    const user = userEvent.setup();
    const fetchMock = routes({
      "POST /api/projects/1/archive": () =>
        json({ freed_bytes: 2_500_000_000, storage: usage({}) }),
    });
    renderPage();

    await user.click(
      await screen.findByRole("button", { name: "Archive First talk" }),
    );
    const confirm = await screen.findByRole("alertdialog", {
      name: "Archive this project?",
    });
    expect(confirm).toHaveTextContent("cannot be undone");
    await user.click(within(confirm).getByRole("button", { name: "Archive" }));

    await waitFor(() =>
      expect(
        callsTo(fetchMock, "POST", "/api/projects/1/archive"),
      ).toHaveLength(1),
    );
    expect(
      await screen.findByText("Project archived. 2.5 GB freed."),
    ).toBeVisible();
  });

  it("does nothing when the archive is cancelled", async () => {
    const user = userEvent.setup();
    const fetchMock = routes();
    renderPage();

    await user.click(
      await screen.findByRole("button", { name: "Archive First talk" }),
    );
    await user.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(
      screen.queryByRole("alertdialog", { name: "Archive this project?" }),
    ).not.toBeInTheDocument();
    expect(callsTo(fetchMock, "POST", "/api/projects/1/archive")).toEqual([]);
  });
});
