import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { WatchEvent, WatchStatus } from "@/api/types";
import { mockRoutes } from "@/testing/mockApi";
import { POLLING, watchEvent, watchRoutes } from "@/testing/watchFixtures";
import { WatchStatusBanner } from "./WatchStatusBanner";
import { RecentAlerts } from "./RecentAlerts";

class FakeNotification {
  static permission = "default";
  static requestPermission = vi.fn(() => {
    FakeNotification.permission = "granted";
    return Promise.resolve("granted");
  });
}

function renderAlerts(events: WatchEvent[], status: WatchStatus = POLLING) {
  mockRoutes(watchRoutes(status, [], events));
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <WatchStatusBanner />
        <RecentAlerts />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Recent alerts", () => {
  it("lists the alerts with the time since publish and the project", async () => {
    renderAlerts(
      [
        watchEvent({
          id: 2,
          platform: "twitch",
          kind: "live",
          source_name: "Afro",
          title: "Raid",
          project_id: null,
          url: "https://www.twitch.tv/afro",
          published_at: null,
          via: "poll",
        }),
        watchEvent(),
      ],
      { ...POLLING, push_available: true },
    );

    expect(await screen.findByRole("status")).toHaveTextContent("Push is on");
    const alerts = await screen.findByRole("list", { name: "Recent alerts" });
    const [live, upload] = within(alerts).getAllByRole("listitem");
    expect(live).toHaveTextContent("Afro is live");
    expect(within(live!).getByRole("link", { name: "Open" })).toHaveAttribute(
      "href",
      "https://www.twitch.tv/afro",
    );
    expect(upload).toHaveTextContent("New upload from YouTube");
    expect(upload).toHaveTextContent("Big news (42 s after publish)");
    expect(
      within(upload!).getByRole("link", { name: "Open project" }),
    ).toHaveAttribute("href", "/projects/7");
  });

  it("asks for desktop alerts", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("Notification", FakeNotification);
    renderAlerts([]);

    expect(await screen.findByText(/No alerts yet/)).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "Enable desktop alerts" }),
    );

    expect(FakeNotification.requestPermission).toHaveBeenCalledOnce();
    expect(await screen.findByText("Desktop alerts on")).toBeVisible();
  });
});
