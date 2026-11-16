import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { SubmissionView } from "@/api/types";
import { callsTo, json, mockRoutes } from "@/testing/mockApi";
import { ReadyToSubmitPage } from "./ReadyToSubmitPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

function view(overrides: Partial<SubmissionView> = {}): SubmissionView {
  return {
    id: 5,
    post_id: 9,
    campaign_id: 1,
    submitted_at: null,
    answered_at: null,
    status: "not_submitted",
    approved_views: null,
    payout_usd: null,
    notes: "",
    platform: "youtube",
    post_url: "https://youtu.be/abc",
    clip_id: 3,
    clip_title: "Big moment",
    campaign_name: "Whop clips",
    copy_text: "https://youtu.be/abc\n\nCampaign: Whop clips",
    ...overrides,
  };
}

/** The API with state: a ticked post leaves the list of those to submit. */
function api(initial: SubmissionView[]) {
  let waiting = initial;
  return mockRoutes({
    "GET /api/submissions?status=not_submitted": () => json(waiting),
    "PATCH /api/submissions/5": () => {
      waiting = waiting.filter((item) => item.id !== 5);
      return json(view({ status: "submitted" }));
    },
  });
}

function renderPage() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <ReadyToSubmitPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ReadyToSubmitPage", () => {
  it("says when nothing is waiting", async () => {
    api([]);
    renderPage();

    expect(await screen.findByText("Nothing to submit")).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Open campaigns" }),
    ).toHaveAttribute("href", "/campaigns");
  });

  it("lists the posts of all campaigns with their campaign and counts them", async () => {
    api([
      view(),
      view({ id: 6, clip_title: "Second one", campaign_name: "Other clips" }),
    ]);
    renderPage();

    expect(await screen.findByText("Big moment")).toBeVisible();
    expect(screen.getByText("Whop clips")).toBeVisible();
    expect(screen.getByText("Other clips")).toBeVisible();
    expect(screen.getByText(/2 published posts are waiting/)).toBeVisible();
  });

  it("copies the post for submission", async () => {
    const user = userEvent.setup();
    api([view()]);
    renderPage();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");

    await user.click(
      await screen.findByRole("button", {
        name: "Copy for submission: Big moment",
      }),
    );

    expect(writeText).toHaveBeenCalledWith(
      "https://youtu.be/abc\n\nCampaign: Whop clips",
    );
  });

  it("ticks a post as submitted and it leaves the list", async () => {
    const user = userEvent.setup();
    const fetchMock = api([view()]);
    renderPage();

    await user.click(
      await screen.findByRole("checkbox", {
        name: /Submitted on the campaign board/,
      }),
    );

    expect(
      JSON.parse(
        String(callsTo(fetchMock, "PATCH", "/api/submissions/5")[0]?.[1]?.body),
      ),
    ).toEqual({ status: "submitted" });
    await waitFor(() =>
      expect(screen.queryByText("Big moment")).not.toBeInTheDocument(),
    );
    expect(await screen.findByText("Nothing to submit")).toBeVisible();
  });
});
