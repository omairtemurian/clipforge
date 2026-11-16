import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, type InitialEntry } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { CollectionClip, CollectionDetail } from "@/api/types";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import { CollectionsPage } from "@/pages/CollectionsPage";
import {
  callsTo,
  job,
  json,
  mockRoutes,
  type Handler,
} from "@/testing/mockApi";

const LIST = [
  {
    id: 9,
    name: "Best bits",
    description: "",
    created_at: "2026-11-01T10:00:00",
    updated_at: "2026-11-01T10:00:00",
    clip_count: 2,
  },
];

function item(position: number, clip: Partial<CollectionClip>) {
  const full: CollectionClip = {
    id: 30 + position,
    project_id: 1,
    title: `Clip ${position}`,
    status: "rendered",
    overall: 80,
    start: 10,
    end: 40,
    ...clip,
  };
  return {
    id: 100 + position,
    collection_id: 9,
    clip_id: full.id,
    position,
    added_at: "2026-11-01T10:00:00",
    clip: full,
  };
}

const DETAIL: CollectionDetail = {
  ...LIST[0],
  items: [item(0, {}), item(1, { status: "candidate", title: "Raw moment" })],
};

function renderAt(path: InitialEntry) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <CollectionsPage />
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
}

function routes(extra: Record<string, Handler> = {}) {
  return mockRoutes({
    "GET /api/collections": () => json(LIST),
    "GET /api/collections/9": () => json(DETAIL),
    ...extra,
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  act(() => clearToasts());
});

describe("Collections page", () => {
  it("lists the collections and opens one", async () => {
    const user = userEvent.setup();
    routes();
    renderAt("/collections");

    expect(screen.getByText("Pick a collection")).toBeVisible();
    await user.click(await screen.findByRole("button", { name: /Best bits/ }));

    const clips = await screen.findByRole("list", { name: "Clips" });
    expect(within(clips).getAllByRole("listitem")).toHaveLength(2);
    expect(within(clips).getByText("Not rendered")).toBeVisible();
    expect(screen.getByText("2 clips · 1 rendered")).toBeVisible();
    expect(screen.getByRole("link", { name: "Download zip" })).toHaveAttribute(
      "href",
      "/api/collections/9/download.zip",
    );
    expect(
      screen.getByRole("link", { name: "Edit Raw moment" }),
    ).toHaveAttribute("href", "/clips/31");
  });

  it("creates a collection and opens it", async () => {
    const user = userEvent.setup();
    const fetchMock = routes({
      "POST /api/collections": () => json({ ...DETAIL, id: 9 }, 201),
    });
    renderAt("/collections");

    await user.type(
      screen.getByRole("textbox", { name: "New collection name" }),
      "Best bits{Enter}",
    );

    const [[, init]] = await waitFor(() => {
      const calls = callsTo(fetchMock, "POST", "/api/collections");
      expect(calls).toHaveLength(1);
      return calls;
    });
    expect(JSON.parse(String(init?.body))).toEqual({ name: "Best bits" });
    expect(await screen.findByRole("list", { name: "Clips" })).toBeVisible();
  });

  it("renders the clips not rendered yet", async () => {
    const user = userEvent.setup();
    const fetchMock = routes({
      "POST /api/clips/31/render": () => json(job({ clip_id: 31 }), 202),
    });
    renderAt("/collections?id=9");

    await user.click(
      await screen.findByRole("button", { name: "Render 1 clip" }),
    );

    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", "/api/clips/31/render")).toHaveLength(
        1,
      ),
    );
    expect(await screen.findByText("Queued")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Render 1 clip" }),
    ).not.toBeInTheDocument();
  });

  it("shows the renders queued by the page that opened it", async () => {
    routes();
    renderAt({
      pathname: "/collections",
      search: "?id=9",
      state: { queued: [31] },
    });

    expect(await screen.findByText("Queued")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Render 1 clip" }),
    ).not.toBeInTheDocument();
  });

  it("removes a clip from the collection", async () => {
    const user = userEvent.setup();
    const fetchMock = routes({
      "DELETE /api/collections/9/items/31": () => json(DETAIL),
    });
    renderAt("/collections?id=9");

    await user.click(
      await screen.findByRole("button", {
        name: "Remove Raw moment from the collection",
      }),
    );

    await waitFor(() =>
      expect(
        callsTo(fetchMock, "DELETE", "/api/collections/9/items/31"),
      ).toHaveLength(1),
    );
  });

  it("renames a collection", async () => {
    const user = userEvent.setup();
    const fetchMock = routes({
      "PATCH /api/collections/9": () => json({ ...DETAIL, name: "Top" }),
    });
    renderAt("/collections?id=9");

    await user.click(
      await screen.findByRole("button", { name: "Rename collection" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Rename collection",
    });
    const field = within(dialog).getByRole("textbox", { name: "Name" });
    await user.clear(field);
    await user.type(field, "Top{Enter}");

    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/collections/9")).toHaveLength(1),
    );
    const [[, init]] = callsTo(fetchMock, "PATCH", "/api/collections/9");
    expect(JSON.parse(String(init?.body))).toEqual({ name: "Top" });
  });

  it("asks before deleting a collection", async () => {
    const user = userEvent.setup();
    const fetchMock = routes({
      "DELETE /api/collections/9": () => new Response(null, { status: 204 }),
    });
    renderAt("/collections?id=9");

    await user.click(
      await screen.findByRole("button", { name: "Delete collection" }),
    );
    const confirm = await screen.findByRole("alertdialog", {
      name: "Delete this collection?",
    });
    expect(callsTo(fetchMock, "DELETE", "/api/collections/9")).toEqual([]);
    await user.click(within(confirm).getByRole("button", { name: "Delete" }));

    await waitFor(() =>
      expect(callsTo(fetchMock, "DELETE", "/api/collections/9")).toHaveLength(
        1,
      ),
    );
    expect(await screen.findByText("Pick a collection")).toBeVisible();
  });
});
