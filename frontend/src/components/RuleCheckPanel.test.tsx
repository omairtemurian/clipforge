import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import { failingCheck } from "@/testing/campaignFixtures";
import { json, mockRoutes } from "@/testing/mockApi";
import { RuleCheckPanel } from "./RuleCheckPanel";

afterEach(() => vi.unstubAllGlobals());

function renderPanel() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RuleCheckPanel clipId={7} />
    </QueryClientProvider>,
  );
}

describe("rule check panel", () => {
  it("shows pass or fail per rule and says publishing is blocked", async () => {
    mockRoutes({
      "GET /api/clips/7/campaign-check": () => json(failingCheck()),
    });
    renderPanel();

    const rules = await screen.findByRole("list", { name: "Campaign rules" });
    expect(
      within(rules).getByRole("listitem", { name: "Campaign is active: pass" }),
    ).toBeVisible();
    const failed = within(rules).getByRole("listitem", {
      name: "Required hashtags: fail",
    });
    expect(failed).toHaveTextContent("Missing hashtags: #afro");
    expect(screen.getByRole("status")).toHaveTextContent(
      "A rule fails. Publishing is blocked",
    );
  });

  it("says that a clip can be published when every rule passes", async () => {
    const check = failingCheck();
    mockRoutes({
      "GET /api/clips/7/campaign-check": () =>
        json({
          ...check,
          passed: true,
          campaign_id: null,
          results: check.results.map((r) => ({ ...r, passed: true })),
        }),
    });
    renderPanel();

    expect(await screen.findByRole("status")).toHaveTextContent(
      "All rules pass",
    );
    expect(screen.getByText(/project has no campaign/)).toBeVisible();
  });

  it("reports a check that cannot load", async () => {
    mockRoutes({});
    renderPanel();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not check the rules.",
    );
  });
});
