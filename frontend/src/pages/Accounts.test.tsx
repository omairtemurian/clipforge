import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { PlatformStatus, SocialAccount } from "@/api/types";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import { callsTo, json, mockRoutes, type Handler } from "@/testing/mockApi";
import { AccountsPage } from "./AccountsPage";

function status(
  platform: PlatformStatus["platform"],
  configured: boolean,
  keys: string[],
  supported = true,
): PlatformStatus {
  return { platform, supported, configured, settings_keys: keys };
}

const PLATFORMS: PlatformStatus[] = [
  status("youtube", true, [
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
  ]),
  status("tiktok", false, ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"]),
  status("instagram", true, ["META_APP_ID", "META_APP_SECRET"]),
  status("facebook", true, ["META_APP_ID", "META_APP_SECRET"]),
  status("x", false, [], false),
  status("linkedin", false, [], false),
];

function account(overrides: Partial<SocialAccount>): SocialAccount {
  return {
    id: 1,
    platform: "youtube",
    external_id: "UC1",
    display_name: "Main channel",
    token_ref: "ref1",
    scopes: [],
    connected_at: "2026-10-31T10:00:00",
    restrictions: ["Unaudited project: uploads are private"],
    is_default: false,
    avatar_url: null,
    always_hashtags: [],
    ...overrides,
  };
}

const YOUTUBE = account({});
const INSTAGRAM = account({
  id: 2,
  platform: "instagram",
  display_name: "clip_page",
  restrictions: [],
  is_default: false,
  avatar_url: null,
});

function routes(
  accounts: SocialAccount[],
  extra: Record<string, Handler> = {},
) {
  let current = accounts;
  return mockRoutes({
    "GET /api/accounts": () => json(current),
    "GET /api/accounts/platforms": () => json(PLATFORMS),
    "DELETE /api/accounts/1": () => {
      current = current.filter((a) => a.id !== 1);
      return new Response(null, { status: 204 });
    },
    ...extra,
  });
}

function renderPage() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <Toaster />
      <AccountsPage />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  clearToasts();
});

describe("AccountsPage", () => {
  it("lists the accounts with restriction badges and filters by platform", async () => {
    const user = userEvent.setup();
    routes([YOUTUBE, INSTAGRAM]);
    renderPage();

    const youtube = await screen.findByRole("listitem", {
      name: "Main channel (YouTube)",
    });
    expect(
      within(youtube).getByText("Unaudited project: uploads are private"),
    ).toBeVisible();
    expect(
      screen.getByRole("listitem", { name: "clip_page (Instagram)" }),
    ).toBeVisible();

    const filters = screen.getByRole("group", { name: "Filter by platform" });
    expect(
      within(filters)
        .getAllByRole("button")
        .map((button) => button.textContent),
    ).toEqual(["All", "YouTube", "TikTok", "Instagram", "Facebook"]);

    await user.click(
      within(filters).getByRole("button", { name: "Instagram" }),
    );
    expect(screen.queryByText("Main channel")).not.toBeInTheDocument();
    expect(screen.getByText("clip_page")).toBeVisible();

    await user.click(within(filters).getByRole("button", { name: "TikTok" }));
    expect(screen.getByText("No TikTok accounts connected yet")).toBeVisible();
  });

  it("shows who is connected, with the avatar, and stars the default account", async () => {
    const user = userEvent.setup();
    let accounts = [
      { ...YOUTUBE, is_default: true, avatar_url: "https://img.test/a.png" },
      { ...account({ id: 3, display_name: "Side channel" }) },
    ];
    const fetchMock = routes([], {
      "GET /api/accounts": () => json(accounts),
      "PUT /api/accounts/3/default": () => {
        accounts = accounts.map((a) => ({ ...a, is_default: a.id === 3 }));
        return json(accounts[1]);
      },
    });
    renderPage();

    const main = await screen.findByRole("listitem", {
      name: "Main channel (YouTube)",
    });
    expect(within(main).getByText(/Connected as/)).toBeVisible();
    expect(
      within(main).getByRole("img", { name: "Main channel's profile picture" }),
    ).toHaveAttribute("src", "https://img.test/a.png");
    expect(
      within(main).getByRole("button", {
        name: "Main channel (YouTube) is the default account",
      }),
    ).toBeDisabled();

    await user.click(
      screen.getByRole("button", {
        name: "Make Side channel (YouTube) the default account",
      }),
    );
    expect(
      await screen.findByRole("button", {
        name: "Side channel (YouTube) is the default account",
      }),
    ).toBeVisible();
    expect(callsTo(fetchMock, "PUT", "/api/accounts/3/default")).toHaveLength(
      1,
    );
  });

  it("edits the hashtags that an account always includes", async () => {
    const user = userEvent.setup();
    const bodies: unknown[] = [];
    const fetchMock = routes([YOUTUBE], {
      "PUT /api/accounts/1/hashtags": (_url, init) => {
        bodies.push(JSON.parse(init?.body as string));
        return json({ ...YOUTUBE, always_hashtags: ["pizza"] });
      },
    });
    renderPage();

    await user.type(
      await screen.findByLabelText("Always include for Main channel (YouTube)"),
      "#pizza{Enter}",
    );
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies).toEqual([{ hashtags: ["pizza"] }]);
    expect(callsTo(fetchMock, "PUT", "/api/accounts/1/hashtags")).toHaveLength(
      1,
    );
  });

  it("removes an account after asking", async () => {
    const user = userEvent.setup();
    const fetchMock = routes([YOUTUBE]);
    renderPage();

    await user.click(
      await screen.findByRole("button", {
        name: "Remove Main channel (YouTube)",
      }),
    );
    expect(callsTo(fetchMock, "DELETE", "/api/accounts/1")).toHaveLength(0);
    await user.click(
      screen.getByRole("button", { name: "Remove Main channel" }),
    );

    await waitFor(() =>
      expect(screen.queryByText("Main channel")).not.toBeInTheDocument(),
    );
    expect(callsTo(fetchMock, "DELETE", "/api/accounts/1")).toHaveLength(1);
    expect(screen.getByText(/No accounts connected yet/)).toBeVisible();
  });

  it("shows the developer app state and the env vars it needs", async () => {
    routes([]);
    renderPage();

    const tiktok = await screen.findByRole("listitem", {
      name: "TikTok developer app",
    });
    expect(within(tiktok).getByText("Needs developer app keys")).toBeVisible();
    expect(
      within(tiktok).getByText(/TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET/),
    ).toBeVisible();
    expect(
      within(
        screen.getByRole("listitem", { name: "YouTube developer app" }),
      ).getByText("Developer app keys are set"),
    ).toBeVisible();
    expect(
      screen.queryByRole("listitem", { name: "X developer app" }),
    ).not.toBeInTheDocument();
  });

  it("connects through a popup and closes the modal once the account shows up", async () => {
    const user = userEvent.setup();
    const popup = { location: { href: "" }, close: vi.fn() };
    const open = vi.fn(() => popup);
    vi.stubGlobal("open", open);
    let accounts: SocialAccount[] = [];
    const fetchMock = routes([], {
      "GET /api/accounts": () => json(accounts),
      "POST /api/accounts/youtube/connect": () =>
        json({
          authorize_url: "https://accounts.google.com/o/oauth2/auth?x=1",
        }),
    });
    renderPage();

    await user.click(
      await screen.findByRole("button", { name: "Add account" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Social account connections",
    });
    expect(
      within(dialog).getByRole("listitem", { name: "TikTok" }),
    ).toHaveTextContent("Needs developer app keys");
    expect(
      within(dialog).queryByRole("button", { name: "Sign in with TikTok" }),
    ).not.toBeInTheDocument();

    await user.click(
      within(dialog).getByRole("button", { name: "Sign in with Google" }),
    );
    await waitFor(() =>
      expect(popup.location.href).toBe(
        "https://accounts.google.com/o/oauth2/auth?x=1",
      ),
    );
    expect(
      callsTo(fetchMock, "POST", "/api/accounts/youtube/connect"),
    ).toHaveLength(1);
    expect(
      await within(dialog).findByText(/Finish in the YouTube window/),
    ).toBeVisible();

    accounts = [YOUTUBE];
    await waitFor(
      () => expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
      { timeout: 5000 },
    );
    expect(await screen.findByText("YouTube account connected.")).toBeVisible();
    expect(
      screen.getByRole("listitem", { name: "Main channel (YouTube)" }),
    ).toBeVisible();
  });

  it("closes the popup and shows the error when connect fails", async () => {
    const user = userEvent.setup();
    const popup = { location: { href: "" }, close: vi.fn() };
    vi.stubGlobal(
      "open",
      vi.fn(() => popup),
    );
    routes([], {
      "POST /api/accounts/instagram/connect": () =>
        json({ error: "needs_credentials", message: "Set META_APP_ID." }, 412),
    });
    renderPage();

    await user.click(
      await screen.findByRole("button", { name: "Add account" }),
    );
    await user.click(
      await screen.findByRole("button", { name: "Sign in with Instagram" }),
    );

    expect(await screen.findByText("Set META_APP_ID.")).toBeVisible();
    expect(popup.close).toHaveBeenCalled();
  });
});
