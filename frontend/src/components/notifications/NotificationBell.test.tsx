import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { Notification } from "@/api/types";
import { callsTo, json, mockRoutes } from "@/testing/mockApi";
import { NotificationBell } from "./NotificationBell";

function note(id: number, overrides: Partial<Notification> = {}): Notification {
  return {
    id,
    kind: "project_done",
    title: `Done ${id}`,
    body: "3 clips are ready.",
    link: "/projects/3",
    created_at: "2026-11-02T10:00:00",
    read_at: null,
    ...overrides,
  };
}

function renderBell() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <NotificationBell />
        <Routes>
          <Route path="/projects/:id" element={<p>Project page</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("NotificationBell", () => {
  it("shows the unread count and opens a notification's link, marking it read", async () => {
    const fetchMock = mockRoutes({
      "GET /api/notifications": () =>
        json({
          items: [note(2), note(1, { read_at: "2026-11-02T11:00:00" })],
          unread_count: 1,
        }),
      "POST /api/notifications/2/read": () =>
        json(note(2, { read_at: "2026-11-02T12:00:00" })),
    });
    renderBell();

    const bell = await screen.findByRole("button", {
      name: "Notifications, 1 unread",
    });
    await userEvent.click(bell);
    expect(screen.getAllByRole("img", { name: "Unread" })).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: /Done 2/ }));

    expect(await screen.findByText("Project page")).toBeVisible();
    expect(
      callsTo(fetchMock, "POST", "/api/notifications/2/read"),
    ).toHaveLength(1);
  });

  it("marks everything read", async () => {
    mockRoutes({
      "GET /api/notifications": () =>
        json({ items: [note(1)], unread_count: 1 }),
      "POST /api/notifications/read-all": () =>
        json({
          items: [note(1, { read_at: "2026-11-02T12:00:00" })],
          unread_count: 0,
        }),
    });
    renderBell();

    await userEvent.click(
      await screen.findByRole("button", { name: /Notifications, 1 unread/ }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Mark all read" }),
    );

    expect(
      await screen.findByRole("button", { name: "Notifications" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Mark all read" }),
    ).toBeDisabled();
  });

  it("says when there is nothing", async () => {
    mockRoutes({
      "GET /api/notifications": () => json({ items: [], unread_count: 0 }),
    });
    renderBell();

    await userEvent.click(
      await screen.findByRole("button", { name: "Notifications" }),
    );

    expect(screen.getByText(/Nothing yet/)).toBeVisible();
  });
});
