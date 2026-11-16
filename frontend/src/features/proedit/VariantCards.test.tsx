import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { Clip, Draft } from "@/api/types";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import { ApprovalInboxPage } from "@/pages/ApprovalInboxPage";
import { Gallery } from "@/pages/Gallery";
import { campaign } from "@/testing/campaignFixtures";
import { approval, draft } from "@/testing/draftFixtures";
import { callsTo, json, mockRoutes, project, scored } from "@/testing/mockApi";
import { CHOICES } from "@/testing/proeditFixtures";

afterEach(() => {
  vi.unstubAllGlobals();
  act(() => clearToasts());
});

const ENABLED = { "GET /api/proedit/status": () => json({ enabled: true }) };
const ORIGINAL: Clip = { ...scored(3, 90, "Big laugh"), status: "rendered" };
const VARIANT: Clip = {
  ...scored(30, 10, "Big laugh — Pro Edit"),
  parent_clip_id: 3,
  variant: "pro_edit",
  status: "rendered",
};

function wrap(children: React.ReactNode) {
  return (
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        {children}
        <Toaster />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Gallery variant cards", () => {
  function api(clips: Clip[]) {
    return mockRoutes({
      ...ENABLED,
      "GET /api/projects/1/clips": () => json(clips),
      "GET /api/projects/1/jobs": () => json([]),
      "GET /api/clips/3": () => json(ORIGINAL),
      "GET /api/projects/1": () => json(project({ id: 1 })),
      "GET /api/proedit/clips/3/choices": () => json(CHOICES),
      "POST /api/proedit/clips/30/render": () =>
        json({ clip: VARIANT, run: {}, job_id: 9 }, 202),
    });
  }

  it("shows a variant right after its original with the badge and link", async () => {
    api([VARIANT, scored(4, 50, "Middle"), ORIGINAL]);
    render(wrap(<Gallery project={project({ id: 1 })} />));

    const cards = await screen.findAllByRole("article");
    expect(cards.map((card) => card.getAttribute("aria-label"))).toEqual([
      "Big laugh",
      "Big laugh — Pro Edit",
      "Middle",
    ]);
    const variant = cards[1];
    expect(within(variant).getByText("Pro Edit")).toBeInTheDocument();
    expect(
      await within(variant).findByRole("link", {
        name: "Pro Edit of “Big laugh”",
      }),
    ).toHaveAttribute("href", "/clips/3");
    expect(
      within(variant).getByRole("link", { name: "Edit clip" }),
    ).toHaveAttribute("href", "/clips/3/proedit?variant=30");
    expect(
      within(variant).queryByRole("button", { name: "Pro Edit" }),
    ).not.toBeInTheDocument();
    expect(within(cards[0]).queryByText("Pro Edit")).not.toBeInTheDocument();
  });

  it("opens the dialog from an original's card", async () => {
    const user = userEvent.setup();
    api([ORIGINAL]);
    render(wrap(<Gallery project={project({ id: 1 })} />));

    await user.click(await screen.findByRole("button", { name: "Pro Edit" }));

    const dialog = await screen.findByRole("dialog", { name: "Pro Edit" });
    expect(within(dialog).getByText(/“Big laugh”/)).toBeInTheDocument();
  });

  it("renders a variant from its plan, not with the v1 render", async () => {
    const user = userEvent.setup();
    const fetchMock = api([ORIGINAL, { ...VARIANT, status: "candidate" }]);
    render(wrap(<Gallery project={project({ id: 1 })} />));

    const card = await screen.findByRole("article", {
      name: "Big laugh — Pro Edit",
    });
    await user.click(within(card).getByRole("button", { name: "Render clip" }));

    await waitFor(() =>
      expect(
        callsTo(fetchMock, "POST", "/api/proedit/clips/30/render"),
      ).toHaveLength(1),
    );
    expect(callsTo(fetchMock, "POST", "/api/clips/30/render")).toHaveLength(0);
  });
});

describe("Inbox variant cards", () => {
  const ORIGINAL_DRAFT = draft({ id: 11, clip_id: 3 });

  function api(drafts: Draft[] = []) {
    const created = draft({ id: 40, clip_id: 30 });
    return mockRoutes({
      ...ENABLED,
      "GET /api/campaigns": () => json([campaign()]),
      "GET /api/drafts?status=pending": () => json([ORIGINAL_DRAFT]),
      "GET /api/drafts?status=needs_fix": () => json([]),
      "GET /api/drafts?campaign_id=1": () => json([ORIGINAL_DRAFT, ...drafts]),
      "GET /api/clips/3": () => json(ORIGINAL),
      "GET /api/projects/1": () => json(project({ id: 1, campaign_id: 1 })),
      "GET /api/proedit/clips/3/variants": () => json([VARIANT]),
      "POST /api/drafts": () => json(created, 201),
      "POST /api/drafts/40/approve": () => json(approval(created)),
      "POST /api/drafts/41/approve": () =>
        json(approval(draft({ id: 41, clip_id: 30 }))),
      "POST /api/drafts/11/approve": () => json(approval(ORIGINAL_DRAFT)),
    });
  }

  function renderInbox() {
    render(wrap(<ApprovalInboxPage />));
  }

  it("approves the Pro Edit through a new draft of it", async () => {
    const user = userEvent.setup();
    const fetchMock = api();
    renderInbox();

    const list = await screen.findByRole("list", { name: "Pro Edit variants" });
    const card = within(list).getByRole("listitem", {
      name: "Pro Edit variant: Big laugh — Pro Edit",
    });
    expect(within(card).getByText("Pro Edit")).toBeInTheDocument();
    await user.click(
      within(card).getByRole("button", { name: "Approve Pro Edit" }),
    );

    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", "/api/drafts/40/approve")).toHaveLength(
        1,
      ),
    );
    const [, init] = callsTo(fetchMock, "POST", "/api/drafts")[0];
    expect(JSON.parse(String(init?.body))).toEqual({ clip_id: 30 });
    expect(callsTo(fetchMock, "POST", "/api/drafts/11/approve")).toHaveLength(
      0,
    );
    expect(await screen.findByText(/^Pro Edit — Approved/)).toBeInTheDocument();
  });

  it("shows the variant's rendered Pro Edit video as its thumbnail", async () => {
    api();
    renderInbox();

    const card = await screen.findByRole("listitem", {
      name: "Pro Edit variant: Big laugh — Pro Edit",
    });
    const video = within(card).getByLabelText(
      "Preview of Big laugh — Pro Edit",
    );
    expect(video.getAttribute("src")).toMatch(
      /^\/api\/proedit\/clips\/30\/video\?v=\w+$/,
    );
  });

  it("approves both with the variant's existing draft", async () => {
    const user = userEvent.setup();
    const fetchMock = api([
      draft({ id: 41, clip_id: 30, status: "needs_fix" }),
    ]);
    renderInbox();

    const list = await screen.findByRole("list", { name: "Pro Edit variants" });
    await user.click(
      within(list).getByRole("button", { name: "Approve both" }),
    );

    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", "/api/drafts/11/approve")).toHaveLength(
        1,
      ),
    );
    expect(callsTo(fetchMock, "POST", "/api/drafts/41/approve")).toHaveLength(
      1,
    );
    expect(callsTo(fetchMock, "POST", "/api/drafts")).toHaveLength(0);
  });

  it("does not approve a Pro Edit whose draft was decided", async () => {
    const user = userEvent.setup();
    const fetchMock = api([draft({ id: 41, clip_id: 30, status: "rejected" })]);
    renderInbox();

    const list = await screen.findByRole("list", { name: "Pro Edit variants" });
    await user.click(
      within(list).getByRole("button", { name: "Approve Pro Edit" }),
    );

    expect(
      await screen.findByText("The Pro Edit's draft is already rejected."),
    ).toBeInTheDocument();
    expect(callsTo(fetchMock, "POST", "/api/drafts/41/approve")).toHaveLength(
      0,
    );
  });
});
