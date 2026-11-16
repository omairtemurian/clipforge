import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { WatchedStreamer } from "@/api/types";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import { callsTo, json, mockRoutes, type Handler } from "@/testing/mockApi";
import { POLLING, streamer, watchRoutes } from "@/testing/watchFixtures";
import { StreamerSection } from "./StreamerSection";

const STREAMERS = "/api/watch/streamers";

function routes(
  streamers: WatchedStreamer[],
  extra: Record<string, Handler> = {},
  status = POLLING,
) {
  return mockRoutes({ ...watchRoutes(status, streamers), ...extra });
}

function renderSection() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <StreamerSection />
      <Toaster />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  act(() => clearToasts());
});

describe("Twitch streamers", () => {
  it("says the Twitch app keys are needed", async () => {
    routes([], {}, { ...POLLING, twitch_configured: false });
    renderSection();

    expect(await screen.findByRole("note")).toHaveTextContent(
      "Needs Twitch app keys",
    );
    expect(screen.getByText(/No streamers yet/)).toBeVisible();
  });

  it("shows a live streamer, how it is watched and its error", async () => {
    routes([
      streamer({ live_since: "2026-10-31T14:00:00", push_state: "subscribed" }),
      streamer({
        id: 6,
        display_name: "Bob",
        last_error: "Twitch has no user named bob",
      }),
    ]);
    renderSection();

    const afro = await screen.findByRole("listitem", { name: "Afro" });
    expect(within(afro).getByText("Live now")).toBeVisible();
    expect(within(afro).getByText("Push")).toBeVisible();
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    const bob = screen.getByRole("listitem", { name: "Bob" });
    expect(within(bob).getByText("Not seen live yet")).toBeVisible();
    expect(within(bob).getByText("Polling every 60 s")).toBeVisible();
    expect(within(bob).getByRole("alert")).toHaveTextContent(
      "Twitch has no user named bob",
    );
  });

  it("adds a streamer by login", async () => {
    const user = userEvent.setup();
    const fetchMock = routes([], {
      [`POST ${STREAMERS}`]: () => json(streamer(), 201),
    });
    renderSection();
    const add = await screen.findByRole("button", { name: "Watch streamer" });
    expect(add).toBeDisabled();

    await user.type(screen.getByLabelText("Twitch streamer"), "afro");
    await user.click(add);

    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", STREAMERS)).toHaveLength(1),
    );
    expect(
      JSON.parse(callsTo(fetchMock, "POST", STREAMERS)[0]?.[1]?.body as string),
    ).toEqual({ login: "afro" });
    expect(await screen.findByText(/Watching the streamer/)).toBeVisible();
    expect(screen.getByLabelText("Twitch streamer")).toHaveValue("");
  });

  it("pauses and removes a streamer", async () => {
    const user = userEvent.setup();
    const fetchMock = routes([streamer()], {
      [`PATCH ${STREAMERS}/5`]: () => json(streamer({ enabled: false })),
      [`DELETE ${STREAMERS}/5`]: () => new Response(null, { status: 204 }),
    });
    renderSection();

    await user.click(
      await screen.findByRole("switch", { name: "Alert when live" }),
    );
    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", `${STREAMERS}/5`)).toHaveLength(1),
    );
    await user.click(screen.getByRole("button", { name: "Remove Afro" }));
    await user.click(screen.getByRole("button", { name: "Remove Afro" }));

    await waitFor(() =>
      expect(callsTo(fetchMock, "DELETE", `${STREAMERS}/5`)).toHaveLength(1),
    );
  });
});
