import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { Asset, Clip, Post, SocialAccount } from "@/api/types";
import { NO_AUDIO_DATA } from "@/testing/assetFixtures";
import { callsTo, clip, json, mockRoutes } from "@/testing/mockApi";
import { SchedulePostModal } from "./SchedulePostModal";

afterEach(() => vi.unstubAllGlobals());

function account(id: number, platform: SocialAccount["platform"]) {
  return {
    id,
    platform,
    external_id: `ext${id}`,
    display_name: `${platform} account`,
    token_ref: `ref${id}`,
    scopes: [],
    connected_at: "2026-11-01T10:00:00",
    restrictions: [],
    is_default: false,
    avatar_url: null,
    always_hashtags: [],
  } satisfies SocialAccount;
}

const YOUTUBE = account(1, "youtube");
const TIKTOK = account(2, "tiktok");

const COVER: Asset = {
  id: 7,
  kind: "image",
  path: "/data/covers/1-3000ms.jpg",
  license: "Frame of the clip",
  attribution: "",
  source_url: null,
  tags: ["thumbnail", "frame", "clip-1"],
  ...NO_AUDIO_DATA,
};

function post(id: number): Post {
  return {
    id,
    clip_id: 1,
    account_id: 1,
    platform: "youtube",
    payload: {},
    thumbnail_asset_id: COVER.id,
    scheduled_at: null,
    status: "draft",
    external_post_id: null,
    url: null,
    error: null,
    attempts: 0,
    attempted_at: null,
    next_attempt_at: null,
  };
}

function bodyOf(call: [string, RequestInit?]): Record<string, unknown> {
  return JSON.parse(String(call[1]?.body)) as Record<string, unknown>;
}

function renderModal(own: Clip = clip()) {
  const onClose = vi.fn();
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <SchedulePostModal clip={own} onClose={onClose} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return onClose;
}

describe("AI post copy in the schedule post modal", () => {
  it("writes each platform's text when it opens", async () => {
    const user = userEvent.setup();
    const fetchMock = mockRoutes({
      "GET /api/accounts": () => json([YOUTUBE, TIKTOK]),
      "POST /api/clips/1/post-copy": (_url, init) => {
        const { platform } = JSON.parse(String(init?.body)) as {
          platform: string;
        };
        return json(
          platform === "youtube"
            ? { title: "AI YouTube title", caption: "Long.", hashtags: ["a"] }
            : { title: "", caption: "AI TikTok caption", hashtags: ["b", "c"] },
        );
      },
    });
    renderModal();

    await user.click(await screen.findByLabelText(/youtube account/));
    await user.click(screen.getByLabelText(/tiktok account/));

    await waitFor(() =>
      expect(screen.getByLabelText("Title")).toHaveValue("AI YouTube title"),
    );
    expect(screen.getByLabelText("Hashtags")).toHaveValue("#a");
    await user.click(screen.getByRole("tab", { name: "TikTok" }));
    expect(screen.getByLabelText("Caption")).toHaveValue("AI TikTok caption");
    expect(screen.getByLabelText("Hashtags")).toHaveValue("#b #c");
    const sent = callsTo(fetchMock, "POST", "/api/clips/1/post-copy");
    expect(sent.map((call) => bodyOf(call).platform).sort()).toEqual([
      "tiktok",
      "youtube",
    ]);
  });

  it("keeps the clip's text and says so when the AI fails", async () => {
    const user = userEvent.setup();
    mockRoutes({
      "GET /api/accounts": () => json([YOUTUBE]),
      "POST /api/clips/1/post-copy": () =>
        json({ error: "llm_error", message: "down" }, 502),
    });
    renderModal();

    await user.click(await screen.findByLabelText(/youtube account/));

    expect(await screen.findByText(/could not write/)).toBeInTheDocument();
    expect(screen.getByLabelText("Title")).toHaveValue("Pizza night");
  });

  it("rewrites with the chosen option from the current text", async () => {
    const user = userEvent.setup();
    const fetchMock = mockRoutes({
      "GET /api/accounts": () => json([YOUTUBE]),
      "POST /api/clips/1/post-copy": (_url, init) =>
        JSON.parse(String(init?.body)).tone
          ? json({ title: "Funny one", caption: "Ha.", hashtags: ["lol"] })
          : json({ title: "First", caption: "First text.", hashtags: ["a"] }),
    });
    renderModal();

    await user.click(await screen.findByLabelText(/youtube account/));
    await waitFor(() =>
      expect(screen.getByLabelText("Title")).toHaveValue("First"),
    );
    await user.type(screen.getByLabelText("Title"), "!");
    await user.click(screen.getByRole("button", { name: "Rewrite with AI" }));
    expect(screen.getByRole("group", { name: "Tone" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Format" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Hashtags" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "funny" }));

    await waitFor(() =>
      expect(screen.getByLabelText("Title")).toHaveValue("Funny one"),
    );
    const rewrite = callsTo(fetchMock, "POST", "/api/clips/1/post-copy")
      .map(bodyOf)
      .find((body) => body.tone);
    expect(rewrite).toMatchObject({
      platform: "youtube",
      tone: "funny",
      format: null,
      hashtags: null,
      current: { title: "First!", caption: "First text.", hashtags: ["a"] },
    });
  });

  it("sends the picked frame as the cover of every post", async () => {
    const user = userEvent.setup();
    const fetchMock = mockRoutes({
      "GET /api/accounts": () => json([YOUTUBE]),
      "POST /api/clips/1/post-copy": () =>
        json({ title: "T", caption: "C", hashtags: ["a"] }),
      "POST /api/clips/1/thumbnail": () => json(COVER, 201),
      "POST /api/clips/1/posts": () => json([post(11)], 201),
      "POST /api/posts/11/publish": () => json(post(11)),
    });
    const onClose = renderModal(clip({ status: "rendered" }));

    await user.click(await screen.findByLabelText(/youtube account/));
    await user.click(screen.getByRole("button", { name: "Use this frame" }));
    expect(await screen.findByAltText("Chosen cover")).toHaveAttribute(
      "src",
      "/api/thumbnails/7",
    );
    await user.click(screen.getByRole("button", { name: "Post now" }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const [frame] = callsTo(fetchMock, "POST", "/api/clips/1/thumbnail");
    expect(bodyOf(frame)).toEqual({ time_s: 0 });
    const [created] = callsTo(fetchMock, "POST", "/api/clips/1/posts");
    expect(bodyOf(created)).toMatchObject({ thumbnail_asset_id: 7 });
  });

  it("uploads an image as the cover and applies it after a bulk schedule", async () => {
    const user = userEvent.setup();
    const fetchMock = mockRoutes({
      "GET /api/accounts": () => json([YOUTUBE]),
      "POST /api/clips/1/post-copy": () =>
        json({ title: "T", caption: "C", hashtags: ["a"] }),
      "POST /api/clips/1/thumbnail/upload": () => json(COVER, 201),
      "POST /api/posts/bulk-schedule": () => json([post(11)], 201),
      "POST /api/clips/1/thumbnail/apply": () => json([post(11)]),
    });
    renderModal(clip({ status: "rendered" }));

    await user.click(await screen.findByLabelText(/youtube account/));
    const file = new File([new Uint8Array([255, 216, 255])], "cover.jpg", {
      type: "image/jpeg",
    });
    await user.upload(screen.getByLabelText("Cover image"), file);
    await screen.findByAltText("Chosen cover");
    await user.click(screen.getByRole("button", { name: "Bulk schedule" }));
    await user.click(
      screen.getByRole("button", { name: "Schedule in free slots" }),
    );

    await waitFor(() =>
      expect(
        callsTo(fetchMock, "POST", "/api/clips/1/thumbnail/apply"),
      ).toHaveLength(1),
    );
    const [applied] = callsTo(
      fetchMock,
      "POST",
      "/api/clips/1/thumbnail/apply",
    );
    expect(bodyOf(applied)).toEqual({ asset_id: 7 });
  });
});
