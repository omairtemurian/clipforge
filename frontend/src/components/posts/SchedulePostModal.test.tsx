import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { Post, SocialAccount } from "@/api/types";
import { callsTo, clip, json, mockRoutes } from "@/testing/mockApi";
import { SchedulePostModal } from "./SchedulePostModal";

afterEach(() => vi.unstubAllGlobals());

const ACCOUNTS: SocialAccount[] = [
  {
    id: 1,
    platform: "youtube",
    external_id: "UC1",
    display_name: "Main channel",
    token_ref: "ref1",
    scopes: [],
    connected_at: "2026-11-01T10:00:00",
    restrictions: [],
    is_default: false,
    avatar_url: null,
    always_hashtags: [],
  },
  {
    id: 2,
    platform: "tiktok",
    external_id: "tt1",
    display_name: "pizza.tok",
    token_ref: "ref2",
    scopes: [],
    connected_at: "2026-11-01T10:00:00",
    restrictions: [],
    is_default: false,
    avatar_url: null,
    always_hashtags: [],
  },
];

function post(id: number, accountId: number): Post {
  return {
    id,
    clip_id: 1,
    account_id: accountId,
    platform: accountId === 1 ? "youtube" : "tiktok",
    payload: {},
    thumbnail_asset_id: null,
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

/** The copy the AI writes: the clip's own text, as without it. */
const COPY = {
  title: "Pizza night",
  caption: "A man and a whole pizza.",
  hashtags: ["pizza", "funny", "standup"],
};

function bodyOf(call: [string, RequestInit?]): unknown {
  return JSON.parse(String(call[1]?.body));
}

function renderModal(onClose = vi.fn()) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <SchedulePostModal clip={clip()} onClose={onClose} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return onClose;
}

describe("schedule post modal", () => {
  it("asks for each platform's text with its account's hashtags", async () => {
    const fetchMock = mockRoutes({
      "GET /api/accounts": () => json(ACCOUNTS),
      "POST /api/clips/1/post-copy": () => json(COPY),
    });
    renderModal();

    await screen.findByLabelText(/Main channel/);
    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", "/api/clips/1/post-copy")).toHaveLength(
        2,
      ),
    );
    const sent = callsTo(fetchMock, "POST", "/api/clips/1/post-copy").map(
      (call) => bodyOf(call),
    );
    expect(sent).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ platform: "youtube", account_id: 1 }),
        expect.objectContaining({ platform: "tiktok", account_id: 2 }),
      ]),
    );
  });

  it("posts now to the chosen accounts with each platform's text", async () => {
    const user = userEvent.setup();
    const fetchMock = mockRoutes({
      "GET /api/accounts": () => json(ACCOUNTS),
      "POST /api/clips/1/post-copy": () => json(COPY),
      "POST /api/clips/1/posts": () => json([post(11, 1), post(12, 2)], 201),
      "POST /api/posts/11/publish": () => json(post(11, 1)),
      "POST /api/posts/12/publish": () => json(post(12, 2)),
    });
    const onClose = renderModal();

    await user.click(await screen.findByLabelText(/Main channel/));
    await user.click(screen.getByLabelText(/pizza.tok/));
    expect(screen.getByLabelText("Title")).toHaveValue("Pizza night");
    const postNow = screen.getByRole("button", { name: "Post now" });
    expect(postNow).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(/TikTok/);

    await user.click(screen.getByRole("tab", { name: "TikTok" }));
    await user.selectOptions(
      screen.getByLabelText("Who can see it"),
      "Only me",
    );
    await user.click(postNow);

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const [created] = callsTo(fetchMock, "POST", "/api/clips/1/posts");
    expect(bodyOf(created)).toMatchObject({
      scheduled_at: null,
      targets: [
        { account_id: 1, text: { title: "Pizza night", privacy: "public" } },
        { account_id: 2, text: { title: "", privacy: "SELF_ONLY" } },
      ],
    });
    expect(callsTo(fetchMock, "POST", "/api/posts/12/publish")).toHaveLength(1);
  });

  it("schedules in each account's free slots with the bulk rules", async () => {
    const user = userEvent.setup();
    const fetchMock = mockRoutes({
      "GET /api/accounts": () => json(ACCOUNTS),
      "POST /api/clips/1/post-copy": () => json(COPY),
      "POST /api/posts/bulk-schedule": () => json([post(11, 1)], 201),
    });
    renderModal();

    await user.click(await screen.findByLabelText(/Main channel/));
    await user.click(screen.getByRole("button", { name: "Bulk schedule" }));
    await user.clear(screen.getByLabelText("Times of day"));
    await user.type(screen.getByLabelText("Times of day"), "18:30");
    await user.click(screen.getByRole("button", { name: "Sun" }));
    await user.click(
      screen.getByRole("button", { name: "Schedule in free slots" }),
    );

    await waitFor(() =>
      expect(
        callsTo(fetchMock, "POST", "/api/posts/bulk-schedule"),
      ).toHaveLength(1),
    );
    const [call] = callsTo(fetchMock, "POST", "/api/posts/bulk-schedule");
    expect(bodyOf(call)).toMatchObject({
      clip_ids: [1],
      queue: true,
      rules: { times: ["18:30"], skip_days: ["sun"], posts_per_day: 1 },
    });
  });
});
