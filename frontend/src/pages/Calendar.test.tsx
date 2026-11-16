import { QueryClientProvider } from "@tanstack/react-query";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { Post } from "@/api/types";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import { callsTo, clip, json, mockRoutes } from "@/testing/mockApi";
import { localIso, post, socialAccount } from "@/testing/postFixtures";
import { CalendarPage } from "./CalendarPage";

const ACCOUNTS = [
  socialAccount({ id: 1, display_name: "Main channel" }),
  socialAccount({ id: 2, platform: "tiktok", display_name: "clips_daily" }),
];

/** Five posts on Nov 3 (2 hidden behind "See 2 more"), one posted on Nov 2. */
const POSTS: Post[] = [
  post({
    id: 10,
    status: "published",
    account_id: 2,
    platform: "tiktok",
    scheduled_at: null,
    attempted_at: localIso(2026, 11, 2, 9, 30),
    payload: { caption: "Posted already\n\n#pizza" },
    url: "https://www.tiktok.com/@clips_daily/video/1",
  }),
  ...[6, 9, 12, 15, 18].map((hour, i) =>
    post({
      id: i + 1,
      scheduled_at: localIso(2026, 11, 3, hour),
      payload: { title: `Clip at ${hour}`, description: "" },
    }),
  ),
  post({
    id: 20,
    status: "canceled",
    scheduled_at: localIso(2026, 11, 4, 9),
    payload: { title: "Canceled one" },
  }),
];

function renderPage(posts = POSTS) {
  const fetchMock = mockRoutes({
    "GET /api/posts": () => json(posts),
    "GET /api/accounts": () => json(ACCOUNTS),
    "GET /api/clips/7": () => json(clip({ id: 7, title: "Pizza night" })),
    "PATCH /api/posts/1": (_url, init) =>
      json({ ...posts[1], ...JSON.parse(String(init?.body)) }),
  });
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <Toaster />
        <CalendarPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

function day(label: string) {
  return screen.getByRole("gridcell", { name: new RegExp(`^${label}\\b`) });
}

function card(title: RegExp) {
  return screen.getByRole("button", { name: title });
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 10, 2, 10, 0));
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  clearToasts();
});

describe("CalendarPage", () => {
  it("shows the month with weekday headers, today and at most 3 cards a day", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(
      screen.getByRole("heading", { name: "November 2026" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("columnheader").map((cell) => cell.textContent),
    ).toEqual([
      "Sunday",
      "Monday",
      "Tuesday",
      "Wednesday",
      "Thursday",
      "Friday",
      "Saturday",
    ]);
    expect(day("Nov 2, today")).toBeInTheDocument();
    const nov3 = day("Nov 3");
    await within(nov3).findByText("Clip at 6");
    expect(within(nov3).getAllByText("Scheduled")).toHaveLength(3);
    expect(within(nov3).queryByText("Clip at 15")).not.toBeInTheDocument();

    await user.click(within(nov3).getByRole("button", { name: "See 2 more" }));
    expect(within(nov3).getByText("Clip at 18")).toBeInTheDocument();
    await user.click(within(nov3).getByRole("button", { name: "See less" }));
    expect(within(nov3).queryByText("Clip at 18")).not.toBeInTheDocument();

    const posted = within(day("Nov 2, today")).getByRole("button", {
      name: /Posted already/,
    });
    expect(within(posted).getByText("Posted")).toBeInTheDocument();
    expect(within(posted).getByText("clips_daily")).toBeInTheDocument();
    expect(within(posted).getByRole("img", { name: "TikTok" })).toBeVisible();
    expect(screen.queryByText("Canceled one")).not.toBeInTheDocument();
  });

  it("reschedules a scheduled card dropped on another day, same time", async () => {
    const fetchMock = renderPage();
    const scheduled = await screen.findByRole("button", { name: /Clip at 6/ });
    const dataTransfer = {
      setData: vi.fn(),
      effectAllowed: "",
      dropEffect: "",
    };

    expect(scheduled).toHaveAttribute("draggable", "true");
    expect(card(/Posted already/)).toHaveAttribute("draggable", "false");

    fireEvent.dragStart(scheduled, { dataTransfer });
    fireEvent.dragOver(day("Nov 9"), { dataTransfer });
    fireEvent.drop(day("Nov 9"), { dataTransfer });

    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/posts/1")).toHaveLength(1),
    );
    const [, init] = callsTo(fetchMock, "PATCH", "/api/posts/1")[0];
    expect(JSON.parse(String(init?.body))).toEqual({
      scheduled_at: localIso(2026, 11, 9, 6),
    });
    expect(await screen.findByText(/^Moved to Nov 9, /)).toBeInTheDocument();
  });

  it("does not move a post to a day already past", async () => {
    const fetchMock = renderPage();
    const scheduled = await screen.findByRole("button", { name: /Clip at 6/ });
    const dataTransfer = {
      setData: vi.fn(),
      effectAllowed: "",
      dropEffect: "",
    };

    fireEvent.dragStart(scheduled, { dataTransfer });
    fireEvent.dragOver(day("Nov 1"), { dataTransfer });
    fireEvent.drop(day("Nov 1"), { dataTransfer });

    expect(await screen.findByText("Pick a day later than now.")).toBeVisible();
    expect(callsTo(fetchMock, "PATCH", "/api/posts/1")).toHaveLength(0);
  });

  it("filters by status, platform and account", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Clip at 6");

    await user.selectOptions(screen.getByLabelText("Status"), "published");
    expect(screen.queryByText("Clip at 6")).not.toBeInTheDocument();
    expect(screen.getByText("Posted already")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Status"), "canceled");
    expect(screen.getByText("Canceled one")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Status"), "all");
    await user.selectOptions(screen.getByLabelText("Platform"), "youtube");
    expect(screen.queryByText("Posted already")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Platform"), "all");
    await user.selectOptions(screen.getByLabelText("Account"), "2");
    expect(screen.getByText("Posted already")).toBeInTheDocument();
    expect(screen.queryByText("Clip at 6")).not.toBeInTheDocument();
  });

  it("switches to the week view with every card and steps between weeks", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Clip at 6");

    await user.click(screen.getByRole("button", { name: "Week" }));
    expect(screen.getAllByRole("gridcell")).toHaveLength(7);
    expect(screen.getByText("Clip at 18")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /more$/ })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Next week" }));
    expect(screen.queryByText("Clip at 6")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Today" }));
    expect(screen.getByText("Clip at 6")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Month" }));
    await user.click(screen.getByRole("button", { name: "Next month" }));
    expect(
      screen.getByRole("heading", { name: "December 2026" }),
    ).toBeInTheDocument();
  });

  it("opens a post's details on click and the bulk scheduler", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(
      await screen.findByRole("button", { name: /Posted already/ }),
    );
    const sheet = screen.getByRole("dialog");
    expect(
      within(sheet).getByRole("link", { name: "Open clip" }),
    ).toHaveAttribute("href", "/clips/7");
    expect(
      within(sheet).getByRole("link", { name: "View post" }),
    ).toHaveAttribute("href", "https://www.tiktok.com/@clips_daily/video/1");
    expect(
      within(sheet).queryByRole("button", { name: "Cancel post" }),
    ).not.toBeInTheDocument();
    await user.click(within(sheet).getByRole("button", { name: "Close" }));

    await user.click(screen.getByRole("button", { name: "Bulk schedule" }));
    expect(
      screen.getByRole("dialog", { name: "Bulk schedule" }),
    ).toBeInTheDocument();
  });
});
