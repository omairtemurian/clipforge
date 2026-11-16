import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { Draft } from "@/api/types";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import { ApprovalInboxPage } from "@/pages/ApprovalInboxPage";
import { campaign } from "@/testing/campaignFixtures";
import { approval, draft, FAILING_RULES } from "@/testing/draftFixtures";
import { callsTo, clip, json, mockRoutes, project } from "@/testing/mockApi";

afterEach(() => {
  vi.unstubAllGlobals();
  act(() => clearToasts());
});

const FIRST = draft({ id: 11, clip_id: 3 });
const SECOND = draft({ id: 12, clip_id: 4, created_at: "2026-11-02T07:00:00" });
const BROKEN = draft({
  id: 13,
  clip_id: 5,
  status: "needs_fix",
  rule_results: FAILING_RULES,
  notes: [{ text: "Check the crop", by: "agent", at: "2026-11-02T09:00:00" }],
});

/** The inbox API with state: decided drafts leave the lists. */
function api() {
  let pending: Draft[] = [FIRST, SECOND];
  const decide = (id: number) => {
    pending = pending.filter((item) => item.id !== id);
  };
  return mockRoutes({
    "GET /api/campaigns": () =>
      json([campaign(), campaign({ id: 2, name: "Other clips" })]),
    "GET /api/drafts?status=pending": () => json(pending),
    "GET /api/drafts?status=needs_fix": () => json([BROKEN]),
    "GET /api/drafts?status=pending&campaign_id=1": () => json(pending),
    "GET /api/drafts?status=needs_fix&campaign_id=1": () => json([BROKEN]),
    "GET /api/clips/3": () =>
      json(clip({ id: 3, title: "Big laugh", hashtags: ["afro", "clips"] })),
    "GET /api/clips/4": () => json(clip({ id: 4, title: "Second moment" })),
    "GET /api/clips/5": () => json(clip({ id: 5, title: "Needs hashtags" })),
    "GET /api/projects/1": () =>
      json(
        project({
          id: 1,
          campaign_id: 1,
          source_url: "https://www.youtube.com/watch?v=abc",
          source_published_at: new Date(
            Date.now() - 5 * 3600_000,
          ).toISOString(),
        }),
      ),
    "POST /api/drafts/11/approve": () => {
      decide(11);
      return json(approval(FIRST));
    },
    "POST /api/drafts/12/approve": () => {
      decide(12);
      return json(approval(SECOND));
    },
    "POST /api/drafts/11/reject": (_url, init) => {
      decide(11);
      const { reason } = JSON.parse(String(init?.body)) as { reason: string };
      return json({ ...FIRST, status: "rejected", reject_reason: reason });
    },
    "POST /api/campaigns/1/drafts/approve": () => {
      const all = pending.map((item) => approval(item));
      pending = [];
      return json(all);
    },
  });
}

function EditorStub() {
  const state = useLocation().state as { backLabel: string };
  return <p>Editor open: {state.backLabel}</p>;
}

function renderInbox() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={["/inbox"]}>
        <Routes>
          <Route path="/inbox" element={<ApprovalInboxPage />} />
          <Route path="/clips/:clipId" element={<EditorStub />} />
        </Routes>
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
}

const card = (title: string) =>
  screen.findByRole("article", { name: `Draft: ${title}` });

describe("ApprovalInboxPage", () => {
  it("shows each draft's preview, text, campaign, rate, score, rules and source", async () => {
    api();
    renderInbox();

    const big = await card("Big laugh");
    expect(within(big).getByLabelText("Preview of Big laugh")).toHaveAttribute(
      "autoplay",
    );
    expect(within(big).getByText("A man and a whole pizza.")).toBeVisible();
    expect(within(big).getByText("#afro #clips")).toBeVisible();
    expect(within(big).getByText("Whop clips")).toBeVisible();
    expect(within(big).getByText("$0.50 per 1,000 views")).toBeVisible();
    expect(
      within(big).getByRole("button", { name: "Score 85, show breakdown" }),
    ).toBeVisible();
    expect(within(big).getByText("All 3 campaign rules pass")).toBeVisible();
    expect(
      await within(big).findByRole("link", { name: /Source video/ }),
    ).toHaveAttribute("href", "https://www.youtube.com/watch?v=abc");
    expect(within(big).getByText("Uploaded 5 h ago")).toBeVisible();
    expect(screen.getByRole("tab", { name: "To approve (2)" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(big).toHaveAttribute("aria-current", "true");
  });

  it("approves a draft into the next free slot", async () => {
    const fetchMock = api();
    renderInbox();
    const big = await card("Big laugh");

    await userEvent.click(within(big).getByRole("button", { name: "Approve" }));

    expect(
      await screen.findByText(/Approved: 1 post scheduled for/),
    ).toBeVisible();
    expect(callsTo(fetchMock, "POST", "/api/drafts/11/approve")).toHaveLength(
      1,
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("article", { name: "Draft: Big laugh" }),
      ).not.toBeInTheDocument(),
    );
    expect(await card("Second moment")).toHaveAttribute("aria-current", "true");
  });

  it("J/K move the selection, A approves and E edits the selected draft", async () => {
    const fetchMock = api();
    renderInbox();
    await card("Second moment");

    await userEvent.keyboard("j");
    expect(await card("Second moment")).toHaveAttribute("aria-current", "true");
    await userEvent.keyboard("k");
    expect(await card("Big laugh")).toHaveAttribute("aria-current", "true");
    await userEvent.keyboard("j");
    await userEvent.keyboard("a");
    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", "/api/drafts/12/approve")).toHaveLength(
        1,
      ),
    );

    await card("Big laugh");
    await userEvent.keyboard("e");
    expect(
      await screen.findByText("Editor open: Back to the approval inbox"),
    ).toBeVisible();
  });

  it("R opens the reason chips and R again rejects with the picked reason", async () => {
    const fetchMock = api();
    renderInbox();
    const big = await card("Big laugh");

    await userEvent.keyboard("r");
    const reasons = within(big).getByRole("group", {
      name: "Why reject Big laugh?",
    });
    await userEvent.click(
      within(reasons).getByRole("button", { name: "Bad crop" }),
    );
    expect(
      within(reasons).getByRole("button", { name: "Bad crop" }),
    ).toHaveAttribute("aria-pressed", "true");
    await userEvent.keyboard("r");

    expect(
      await screen.findByText("Rejected. The autopilot learns from it."),
    ).toBeVisible();
    const [call] = callsTo(fetchMock, "POST", "/api/drafts/11/reject");
    expect(JSON.parse(String(call[1]?.body))).toEqual({ reason: "bad_crop" });
  });

  it("Escape closes the reason chips and Reject clip rejects with no reason", async () => {
    const fetchMock = api();
    renderInbox();
    const big = await card("Big laugh");

    await userEvent.click(within(big).getByRole("button", { name: "Reject" }));
    await userEvent.keyboard("{Escape}");
    expect(
      within(big).queryByRole("group", { name: "Why reject Big laugh?" }),
    ).not.toBeInTheDocument();

    await userEvent.click(within(big).getByRole("button", { name: "Reject" }));
    await userEvent.click(
      within(big).getByRole("button", { name: "Reject clip" }),
    );
    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", "/api/drafts/11/reject")).toHaveLength(
        1,
      ),
    );
    const [call] = callsTo(fetchMock, "POST", "/api/drafts/11/reject");
    expect(JSON.parse(String(call[1]?.body))).toEqual({ reason: null });
  });

  it("lists the drafts that fail a rule in the Needs fix tab", async () => {
    api();
    renderInbox();
    await card("Big laugh");

    await userEvent.click(screen.getByRole("tab", { name: "Needs fix (1)" }));

    const broken = await card("Needs hashtags");
    expect(
      within(broken).getByText("1 of 3 campaign rules fail"),
    ).toBeVisible();
    expect(
      within(broken).getAllByLabelText("Required hashtags: fail")[0],
    ).toBeVisible();
    expect(within(broken).getByText("Check the crop")).toBeVisible();
    expect(
      screen.queryByRole("article", { name: "Draft: Big laugh" }),
    ).not.toBeInTheDocument();
  });

  it("approves all waiting drafts of the chosen campaign after a confirm", async () => {
    const fetchMock = api();
    renderInbox();
    await card("Big laugh");
    const approveAll = screen.getByRole("button", {
      name: "Approve all for this campaign",
    });
    expect(approveAll).toBeDisabled();

    await userEvent.selectOptions(screen.getByLabelText("Campaign"), "1");
    await waitFor(() => expect(approveAll).toBeEnabled());
    await userEvent.click(approveAll);
    const dialog = await screen.findByRole("alertdialog", {
      name: "Approve 2 clips?",
    });
    expect(
      callsTo(fetchMock, "POST", "/api/campaigns/1/drafts/approve"),
    ).toEqual([]);
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Approve all" }),
    );

    expect(
      await screen.findByText("Approved 2 clips of Whop clips."),
    ).toBeVisible();
    expect(
      callsTo(fetchMock, "POST", "/api/campaigns/1/drafts/approve"),
    ).toHaveLength(1);
    expect(await screen.findByText("Nothing to approve")).toBeVisible();
  });
});
