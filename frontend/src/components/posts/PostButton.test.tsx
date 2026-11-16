import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { Clip, Job, Post, SocialAccount } from "@/api/types";
import { callsTo, clip, json, mockRoutes } from "@/testing/mockApi";
import { PostButton } from "./PostButton";

afterEach(() => vi.unstubAllGlobals());
beforeEach(() => localStorage.clear());

function account(id: number, overrides: Partial<SocialAccount>): SocialAccount {
  return {
    id,
    platform: "youtube",
    external_id: `ext${id}`,
    display_name: `Account ${id}`,
    token_ref: `ref${id}`,
    scopes: [],
    connected_at: "2026-11-01T10:00:00",
    restrictions: [],
    is_default: false,
    avatar_url: null,
    always_hashtags: [],
    ...overrides,
  };
}

const ACCOUNTS = [
  account(1, { display_name: "Main channel", is_default: true }),
  account(2, { display_name: "Side channel" }),
  account(3, { platform: "instagram", display_name: "clip_page" }),
];

const COPY = { title: "AI title", caption: "AI caption", hashtags: ["ai"] };

const POST = {
  id: 11,
  clip_id: 1,
  account_id: 1,
  platform: "youtube",
  status: "queued",
} as Post;

function bodyOf(call: [string, RequestInit?]): unknown {
  return JSON.parse(String(call[1]?.body));
}

function renderButton(target: Clip = clip({ status: "rendered" })) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <PostButton clip={target} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const ROUTES = {
  "GET /api/accounts": () => json(ACCOUNTS),
  "POST /api/clips/1/post-copy": () => json(COPY),
  "POST /api/clips/1/quick-post": () => json([POST], 201),
};

describe("post split button", () => {
  it("posts in one click to each platform's default account", async () => {
    const user = userEvent.setup();
    const fetchMock = mockRoutes(ROUTES);
    renderButton();

    await user.click(screen.getByRole("button", { name: "Post" }));
    const dialog = await screen.findByRole("dialog", { name: "Post clip" });
    expect(await screen.findByLabelText(/Main channel/)).toBeChecked();
    expect(screen.queryByLabelText(/Side channel/)).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByLabelText("Title")).toHaveValue("AI title"),
    );
    const postNow = screen.getByRole("button", { name: "Post now" });
    await waitFor(() => expect(postNow).toBeEnabled());
    await user.click(postNow);

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    const [call] = callsTo(fetchMock, "POST", "/api/clips/1/quick-post");
    expect(bodyOf(call)).toMatchObject({
      platforms: ["youtube", "instagram"],
      texts: { youtube: { title: "AI title", caption: "AI caption" } },
    });
    expect(callsTo(fetchMock, "POST", "/api/clips/1/render")).toHaveLength(0);
  });

  it("remembers the platforms of the last post", async () => {
    const user = userEvent.setup();
    const fetchMock = mockRoutes(ROUTES);
    renderButton();

    await user.click(screen.getByRole("button", { name: "Post" }));
    await user.click(await screen.findByLabelText(/clip_page/));
    const postNow = screen.getByRole("button", { name: "Post now" });
    await waitFor(() => expect(postNow).toBeEnabled());
    await user.click(postNow);
    await waitFor(() =>
      expect(
        callsTo(fetchMock, "POST", "/api/clips/1/quick-post"),
      ).toHaveLength(1),
    );
    expect(localStorage.getItem("clipforge.quickPost.platforms")).toBe(
      '["youtube"]',
    );
  });

  it("renders the clip first when it is not rendered", async () => {
    const user = userEvent.setup();
    const fetchMock = mockRoutes({
      ...ROUTES,
      "POST /api/clips/1/render": () => json({ id: 5 } as Job),
      "GET /api/clips/1": () => json(clip({ status: "rendering" })),
    });
    renderButton(clip({ status: "candidate" }));

    await user.click(screen.getByRole("button", { name: "Post" }));
    expect(await screen.findByText("Rendering the clip…")).toBeVisible();
    expect(screen.getByRole("button", { name: "Post now" })).toBeDisabled();
    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", "/api/clips/1/render")).toHaveLength(1),
    );
  });

  it("chooses accounts from the menu and posts to them", async () => {
    const user = userEvent.setup();
    const fetchMock = mockRoutes(ROUTES);
    renderButton();

    await user.click(
      screen.getByRole("button", { name: "More posting options" }),
    );
    await user.click(screen.getByRole("button", { name: "Choose accounts…" }));
    await user.click(await screen.findByLabelText(/Side channel/));
    const postNow = screen.getByRole("button", { name: "Post now" });
    await waitFor(() => expect(postNow).toBeEnabled());
    await user.click(postNow);

    await waitFor(() =>
      expect(
        callsTo(fetchMock, "POST", "/api/clips/1/quick-post"),
      ).toHaveLength(1),
    );
    const [call] = callsTo(fetchMock, "POST", "/api/clips/1/quick-post");
    expect(bodyOf(call)).toMatchObject({ account_ids: [1, 2, 3] });
  });

  it("opens the schedule modal from the menu", async () => {
    const user = userEvent.setup();
    mockRoutes(ROUTES);
    renderButton();

    await user.click(
      screen.getByRole("button", { name: "More posting options" }),
    );
    await user.click(screen.getByRole("button", { name: "Schedule…" }));
    expect(
      await screen.findByRole("dialog", { name: "Schedule post" }),
    ).toBeVisible();
  });

  it("points to the Social accounts page without an account", async () => {
    const user = userEvent.setup();
    mockRoutes({ ...ROUTES, "GET /api/accounts": () => json([]) });
    renderButton();

    await user.click(screen.getByRole("button", { name: "Post" }));
    expect(
      await screen.findByRole("link", {
        name: "Sign in on the Social accounts page",
      }),
    ).toHaveAttribute("href", "/accounts");
    expect(screen.getByRole("button", { name: "Post now" })).toBeDisabled();
  });
});
