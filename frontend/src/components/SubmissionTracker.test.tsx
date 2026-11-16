import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { SubmissionView } from "@/api/types";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import { callsTo, json, mockRoutes } from "@/testing/mockApi";
import { SubmissionTracker } from "./SubmissionTracker";

afterEach(() => {
  vi.unstubAllGlobals();
  act(() => clearToasts());
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

function api(initial: SubmissionView[]) {
  let current = initial;
  return mockRoutes({
    "GET /api/submissions?campaign_id=1": () => json(current),
    "PATCH /api/submissions/5": (_url, init) => {
      const patch = JSON.parse(String(init?.body)) as Partial<SubmissionView>;
      current = current.map((item) => ({ ...item, ...patch }));
      return json(current[0]);
    },
  });
}

function renderTracker(rate: number | null = null) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <SubmissionTracker campaignId={1} rate={rate} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("SubmissionTracker", () => {
  it("says when there is nothing to submit", async () => {
    api([]);
    renderTracker();
    expect(await screen.findByText("Nothing to submit yet")).toBeVisible();
  });

  it("copies the post for submission", async () => {
    const user = userEvent.setup();
    api([view()]);
    renderTracker();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");

    await user.click(
      await screen.findByRole("button", {
        name: "Copy for submission: Big moment",
      }),
    );

    expect(writeText).toHaveBeenCalledWith(
      "https://youtu.be/abc\n\nCampaign: Whop clips",
    );
    expect(await screen.findByText("Copied")).toBeVisible();
  });

  it("ticks a post as submitted, then saves the board's answer", async () => {
    const user = userEvent.setup();
    const fetchMock = api([view()]);
    renderTracker();

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

    const form = await screen.findByRole("form", {
      name: "Details of Big moment",
    });
    const save = within(form).getByRole("button", { name: "Save details" });
    expect(save).toBeDisabled();
    await user.selectOptions(
      within(form).getByLabelText("Answer of the board"),
      "approved",
    );
    await user.type(within(form).getByLabelText("Approved views"), "1200");
    await user.click(save);

    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/submissions/5")).toHaveLength(2),
    );
    expect(
      JSON.parse(
        String(callsTo(fetchMock, "PATCH", "/api/submissions/5")[1]?.[1]?.body),
      ),
    ).toEqual({ status: "approved", approved_views: 1200 });
  });

  it("does not save a number that is not allowed", async () => {
    const user = userEvent.setup();
    api([view({ status: "submitted" })]);
    renderTracker();

    const form = await screen.findByRole("form", {
      name: "Details of Big moment",
    });
    await user.type(within(form).getByLabelText("Payout (USD)"), "-1");

    expect(
      within(form).getByRole("button", { name: "Save details" }),
    ).toBeDisabled();
    expect(
      within(form).getByText("Use a number, 0 or more."),
    ).toBeInTheDocument();
  });

  it("adds up the approved views, the estimate and the payouts", async () => {
    api([
      view({ status: "paid", approved_views: 12_345, payout_usd: 30 }),
      view({ id: 6, status: "approved", approved_views: 1_000 }),
      view({ id: 7, status: "rejected", approved_views: 500 }),
    ]);
    renderTracker(2.5);

    const earnings = await screen.findByRole("region", { name: "Earnings" });
    const figure = (label: string) =>
      within(earnings).getByText(label).nextElementSibling?.textContent;
    expect(figure("Approved views")).toBe("13,345");
    expect(figure("Estimated earnings")).toBe("$33.36");
    expect(figure("Payouts")).toBe("$30.00");
    expect(within(earnings).getByText(/^Estimate: /)).toHaveTextContent(
      "approved views / 1,000 × $2.50",
    );
  });

  it("has no estimate without a rate", async () => {
    api([view({ status: "approved", approved_views: 900 })]);
    renderTracker(null);

    const earnings = await screen.findByRole("region", { name: "Earnings" });
    expect(within(earnings).getByText("No rate set")).toBeVisible();
  });
});
