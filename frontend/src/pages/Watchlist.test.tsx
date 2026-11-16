import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { WatchedChannel, WatchedVideo } from "@/api/types";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import {
  DEFAULTS,
  callsTo,
  captionTemplate,
  json,
  mockRoutes,
  type Handler,
} from "@/testing/mockApi";
import {
  CHANNEL_ID,
  watchRoutes,
  watchedChannel,
} from "@/testing/watchFixtures";
import { WatchlistPage } from "./Watchlist";

const CHANNELS = "/api/auto-import/channels";
const YOUTUBE = watchedChannel();

function video(id: string, project_id: number | null): WatchedVideo {
  return {
    watched_channel_id: 1,
    video_id: id,
    title: `Video ${id}`,
    published_at: null,
    project_id,
    seen_at: "2026-10-31T11:00:00",
  };
}

function routes(
  channels: WatchedChannel[],
  videos: WatchedVideo[] = [],
  extra: Record<string, Handler> = {},
) {
  return mockRoutes({
    [`GET ${CHANNELS}`]: () => json(channels),
    [`GET ${CHANNELS}/1/videos`]: () => json(videos),
    "GET /api/processing-defaults": () => json(DEFAULTS),
    "GET /api/caption-templates": () =>
      json(["karaoke_bold"].map(captionTemplate)),
    "GET /api/brand-templates": () => json([]),
    "GET /api/speech-languages": () => json([{ code: "en", name: "English" }]),
    "GET /api/processing-presets": () => json([]),
    ...watchRoutes(),
    ...extra,
  });
}

function renderPage() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <WatchlistPage />
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  act(() => clearToasts());
});

describe("Watchlist page", () => {
  it("says whether push is on and how each channel is watched", async () => {
    routes([
      YOUTUBE,
      watchedChannel({
        id: 2,
        title: "Push",
        push_state: "failed",
        push_error: "hub answered 500",
      }),
    ]);
    renderPage();

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Polling every 60 s. Set PUBLIC_CALLBACK_URL",
    );
    const card = await screen.findByRole("listitem", { name: "YouTube" });
    expect(within(card).getByText("Polling every 60 s")).toBeVisible();
    const failed = screen.getByRole("listitem", { name: "Push" });
    expect(
      within(failed).getByText("Polling every 60 s (push failed)"),
    ).toBeVisible();
    expect(
      within(failed).getByText(/Push is off \(hub answered 500\)/),
    ).toBeVisible();
  });

  it("says so when no channel is watched", async () => {
    routes([]);
    renderPage();

    expect(await screen.findByText(/No channels yet/)).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Watch channel" }),
    ).toBeDisabled();
  });

  it("shows each channel with last checked and the projects it made", async () => {
    routes([YOUTUBE], [video("a", 7), video("b", null)]);
    renderPage();

    const card = await screen.findByRole("listitem", { name: "YouTube" });
    expect(
      await within(card).findByText(/Checked .* · 1 new project/),
    ).toBeVisible();
    expect(within(card).getByText(/Comedy · 3 clips · 9:16/)).toBeVisible();
    expect(within(card).getByRole("link", { name: "Video a" })).toHaveAttribute(
      "href",
      "/projects/7",
    );
    expect(within(card).queryByText("Video b")).not.toBeInTheDocument();
  });

  it("says that the videos already on a channel are skipped", async () => {
    routes([YOUTUBE], [video("a", null), video("b", null)]);
    renderPage();

    const card = await screen.findByRole("listitem", { name: "YouTube" });
    expect(
      await within(card).findByText(/No video has been imported yet/),
    ).toHaveTextContent("The 2 already on the channel are skipped.");
    expect(within(card).getByText(/No new projects yet/)).toBeVisible();
  });

  it("shows the error of a feed that could not be read", async () => {
    routes([{ ...YOUTUBE, last_error: "feed answered 404" }]);
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not read the channel's feed: feed answered 404",
    );
  });

  it("adds a channel with the saved defaults once the rights are chosen", async () => {
    const user = userEvent.setup();
    const fetchMock = routes([], [], {
      [`POST ${CHANNELS}`]: () => json({ ...YOUTUBE, title: "" }, 201),
    });
    renderPage();
    const add = await screen.findByRole("button", { name: "Watch channel" });

    await user.type(
      screen.getByLabelText("YouTube channel"),
      `https://www.youtube.com/channel/${CHANNEL_ID}`,
    );
    expect(add).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Source rights"), "cc_by");
    await user.type(screen.getByLabelText("Credit line"), "Video by Ann");
    await waitFor(() => expect(add).toBeEnabled());
    await user.click(add);

    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", CHANNELS)).toHaveLength(1),
    );
    const body = JSON.parse(
      callsTo(fetchMock, "POST", CHANNELS)[0]?.[1]?.body as string,
    );
    expect(body).toEqual({
      channel: `https://www.youtube.com/channel/${CHANNEL_ID}`,
      settings: DEFAULTS,
      source_rights: "cc_by",
      credit_line: "Video by Ann",
    });
    expect(await screen.findByText(/Watching the channel/)).toBeVisible();
    expect(screen.getByLabelText("YouTube channel")).toHaveValue("");
  });

  it("shows the server's message when a channel cannot be added", async () => {
    const user = userEvent.setup();
    routes([], [], {
      [`POST ${CHANNELS}`]: () =>
        json({ error: "conflict", message: "channel is already watched" }, 409),
    });
    renderPage();
    const add = await screen.findByRole("button", { name: "Watch channel" });

    await user.type(screen.getByLabelText("YouTube channel"), CHANNEL_ID);
    await user.selectOptions(screen.getByLabelText("Source rights"), "own");
    await waitFor(() => expect(add).toBeEnabled());
    await user.click(add);

    expect(await screen.findByText("channel is already watched")).toBeVisible();
  });

  it("edits the defaults of a channel", async () => {
    const user = userEvent.setup();
    const fetchMock = routes([YOUTUBE], [], {
      [`PATCH ${CHANNELS}/1`]: () => json(YOUTUBE),
    });
    renderPage();

    await user.click(
      await screen.findByRole("button", { name: "Edit defaults of YouTube" }),
    );
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Genre")).toHaveValue("comedy");
    expect(within(dialog).queryByText(/Upload SRT/)).not.toBeInTheDocument();
    await user.selectOptions(within(dialog).getByLabelText("Genre"), "gaming");
    await user.selectOptions(
      within(dialog).getByLabelText("Source rights"),
      "own",
    );
    await user.click(
      within(dialog).getByRole("switch", { name: "Schedule clips as drafts" }),
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Save defaults" }),
    );

    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", `${CHANNELS}/1`)).toHaveLength(1),
    );
    const patch = JSON.parse(
      callsTo(fetchMock, "PATCH", `${CHANNELS}/1`)[0]?.[1]?.body as string,
    );
    expect(patch).toMatchObject({
      settings: { genre: "gaming", num_clips: 3 },
      source_rights: "own",
      credit_line: "Video by YouTube",
      auto_schedule_drafts: true,
    });
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });

  it("pauses a channel with its switch", async () => {
    const user = userEvent.setup();
    const fetchMock = routes([YOUTUBE], [], {
      [`PATCH ${CHANNELS}/1`]: () => json({ ...YOUTUBE, enabled: false }),
    });
    renderPage();

    await user.click(
      await screen.findByRole("switch", { name: "Import new videos" }),
    );

    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", `${CHANNELS}/1`)).toHaveLength(1),
    );
    expect(
      JSON.parse(
        callsTo(fetchMock, "PATCH", `${CHANNELS}/1`)[0]?.[1]?.body as string,
      ),
    ).toEqual({ enabled: false });
  });

  it("removes a channel after a confirmation", async () => {
    const user = userEvent.setup();
    const fetchMock = routes([YOUTUBE], [], {
      [`DELETE ${CHANNELS}/1`]: () => new Response(null, { status: 204 }),
    });
    renderPage();

    await user.click(
      await screen.findByRole("button", { name: "Remove YouTube" }),
    );
    expect(callsTo(fetchMock, "DELETE", `${CHANNELS}/1`)).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Keep" }));
    await user.click(screen.getByRole("button", { name: "Remove YouTube" }));
    await user.click(screen.getByRole("button", { name: "Remove YouTube" }));

    await waitFor(() =>
      expect(callsTo(fetchMock, "DELETE", `${CHANNELS}/1`)).toHaveLength(1),
    );
  });
});
