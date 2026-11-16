import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { WatchEvent } from "@/api/types";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import { json, mockApi } from "@/testing/mockApi";
import { watchEvent } from "@/testing/watchFixtures";
import { useWatchAlerts } from "./useWatchAlerts";

const shown: { title: string; body?: string }[] = [];

class FakeNotification {
  static permission = "granted";
  constructor(title: string, options?: { body?: string }) {
    shown.push({ title, body: options?.body });
  }
}

function Alerts() {
  useWatchAlerts(1000);
  return null;
}

/** Answer GET /watch/events?after=N from the events with an id above N. */
function serve(events: WatchEvent[]) {
  return mockApi((url) => {
    const after = Number(new URL(url, "http://x").searchParams.get("after"));
    return json(events.filter((event) => event.id > after).reverse());
  });
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.stubGlobal("Notification", FakeNotification);
  shown.length = 0;
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  act(() => clearToasts());
});

describe("useWatchAlerts", () => {
  it("alerts on new events only, as a toast and on the desktop", async () => {
    const events = [watchEvent({ id: 1, title: "Old video" })];
    const fetchMock = serve(events);
    render(
      <QueryClientProvider client={createQueryClient()}>
        <Alerts />
        <Toaster />
      </QueryClientProvider>,
    );
    await act(() => vi.advanceTimersByTimeAsync(10));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/watch/events?after=0",
      expect.anything(),
    );

    events.push(
      watchEvent({ id: 2 }),
      watchEvent({ id: 3, kind: "live", source_name: "Afro", title: "Raid" }),
    );
    await act(() => vi.advanceTimersByTimeAsync(1000));

    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/watch/events?after=1",
      expect.anything(),
    );
    expect(
      await screen.findByText(
        "New upload from YouTube: Big news (42 s after publish)",
      ),
    ).toBeVisible();
    expect(screen.queryByText(/Old video/)).not.toBeInTheDocument();
    expect(shown.map((alert) => alert.title)).toEqual([
      "New upload from YouTube",
      "Afro is live",
    ]);

    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/watch/events?after=3",
      expect.anything(),
    );
    expect(shown).toHaveLength(2);
  });

  it("stays quiet when the server cannot be reached", async () => {
    mockApi(() => {
      throw new TypeError("Failed to fetch");
    });
    render(
      <QueryClientProvider client={createQueryClient()}>
        <Alerts />
        <Toaster />
      </QueryClientProvider>,
    );
    await act(() => vi.advanceTimersByTimeAsync(2100));

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(shown).toEqual([]);
  });
});
