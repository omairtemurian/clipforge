import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { Post } from "@/api/types";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import { callsTo, clip, json, mockRoutes } from "@/testing/mockApi";
import { localIso, post, socialAccount } from "@/testing/postFixtures";
import { PostHistoryPage } from "./PostHistoryPage";

const ACCOUNTS = [
  socialAccount({ id: 1, display_name: "Main channel" }),
  socialAccount({ id: 2, platform: "tiktok", display_name: "clips_daily" }),
];

const SKIPPED = "Skipped: it was due while ClipForge was off.";

/** Newest first, as GET /posts/history answers. */
const HISTORY: Post[] = [
  post({
    id: 3,
    status: "published",
    account_id: 2,
    platform: "tiktok",
    attempted_at: localIso(2026, 11, 2, 15),
    payload: { caption: "Hot slice\n\n#pizza" },
    url: "https://www.tiktok.com/@clips_daily/video/3",
  }),
  post({
    id: 2,
    status: "skipped",
    scheduled_at: localIso(2026, 11, 2, 9),
    payload: { title: "Missed one" },
    error: SKIPPED,
  }),
  post({
    id: 1,
    status: "failed",
    account_id: null,
    attempted_at: localIso(2026, 11, 1, 9),
    payload: { title: "Too big" },
    error: "The video is too large.",
  }),
];

const HISTORY_URL = "/api/posts/history?limit=50";

function renderPage(history = HISTORY) {
  const fetchMock = mockRoutes({
    [`GET ${HISTORY_URL}`]: () => json(history),
    [`GET ${HISTORY_URL}&status=skipped`]: () =>
      json(history.filter((each) => each.status === "skipped")),
    "GET /api/accounts": () => json(ACCOUNTS),
    "GET /api/clips/7": () => json(clip({ id: 7, title: "Pizza night" })),
    "POST /api/posts/2/publish": () =>
      json({ ...HISTORY[1], status: "queued", error: null }),
  });
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <Toaster />
        <PostHistoryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

afterEach(clearToasts);

describe("PostHistoryPage", () => {
  it("lists the finished posts with the links to the live posts", async () => {
    renderPage();

    const list = await screen.findByRole("list", { name: "Posts" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByText("Hot slice")).toBeVisible();
    expect(within(rows[0]).getByText("Posted")).toBeVisible();
    expect(
      within(rows[0]).getByRole("link", { name: "View post" }),
    ).toHaveAttribute("href", "https://www.tiktok.com/@clips_daily/video/3");
    expect(within(rows[0]).getByText(/clips_daily · TikTok/)).toBeVisible();
    expect(within(rows[1]).getByText("Skipped")).toBeVisible();
    expect(within(rows[1]).getByText(SKIPPED)).toBeVisible();
    expect(
      within(rows[1]).queryByRole("link", { name: "View post" }),
    ).toBeNull();
    expect(within(rows[2]).getByText(/Disconnected account/)).toBeVisible();
    expect(within(rows[2]).getByText("The video is too large.")).toBeVisible();
    expect(
      within(rows[2]).getByRole("link", { name: "Open clip" }),
    ).toHaveAttribute("href", "/clips/7");
  });

  it("filters by status", async () => {
    const fetchMock = renderPage();
    await screen.findByRole("list", { name: "Posts" });

    await userEvent.selectOptions(screen.getByLabelText("Status"), "Skipped");

    await waitFor(() =>
      expect(screen.getAllByRole("listitem")).toHaveLength(1),
    );
    expect(
      callsTo(fetchMock, "GET", `${HISTORY_URL}&status=skipped`),
    ).toHaveLength(1);
  });

  it("posts a skipped post now from its details", async () => {
    const fetchMock = renderPage();

    await userEvent.click(
      await screen.findByRole("button", { name: "Missed one" }),
    );
    const sheet = await screen.findByRole("dialog");
    expect(within(sheet).getByRole("alert")).toHaveTextContent(SKIPPED);
    await userEvent.click(
      within(sheet).getByRole("button", { name: "Post now" }),
    );

    expect(await screen.findByText("Posting now.")).toBeVisible();
    expect(callsTo(fetchMock, "POST", "/api/posts/2/publish")).toHaveLength(1);
  });

  it("says when nothing was posted yet", async () => {
    renderPage([]);

    expect(await screen.findByText("Nothing posted yet")).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Open the calendar" }),
    ).toHaveAttribute("href", "/calendar");
  });
});
