import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { AutopilotSettings } from "@/api/types";
import { campaign } from "@/testing/campaignFixtures";
import { json, mockApi } from "@/testing/mockApi";
import { CampaignProEdit } from "./CampaignProEdit";

const SETTINGS: AutopilotSettings = {
  campaign_id: 1,
  enabled: true,
  max_clips_per_source: 3,
  slots: null,
  max_posts_per_day: 3,
  draft_ttl_days: 3,
  account_ids: [4],
  min_clip_s: null,
  max_clip_s: null,
  caption_template: null,
  brand_template_id: null,
  proedit_enabled: false,
  proedit_preset: "clean_pro",
  proedit_max_intensity: "standard",
};

/** The API of campaign 1: Pro Edit on or off, the autopilot settings. */
function api(enabled = true) {
  return mockApi((url, init) => {
    const method = init?.method ?? "GET";
    if (url === "/api/proedit/status") {
      return enabled
        ? json({ enabled: true, critic_max_rounds: 2 })
        : json({ error: "proedit_disabled", message: "off" }, 404);
    }
    if (url === "/api/campaigns/1/autopilot" && method === "GET") {
      return json(SETTINGS);
    }
    if (url === "/api/campaigns/1/autopilot" && method === "PUT") {
      return json({ ...JSON.parse(String(init?.body)), campaign_id: 1 });
    }
    if (url === "/api/campaigns/1" && method === "PATCH") {
      return json(campaign({ ...JSON.parse(String(init?.body)) }));
    }
    return json({ error: "not_found", message: `no route ${url}` }, 404);
  });
}

function renderSection() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <CampaignProEdit campaign={campaign({ id: 1 })} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("CampaignProEdit", () => {
  it("starts off, warns while heavy edits are not allowed and saves both", async () => {
    const user = userEvent.setup();
    const fetchMock = api();
    renderSection();

    const toggle = await screen.findByRole("switch", {
      name: "Also make a Pro Edit variant",
    });
    expect(toggle).not.toBeChecked();
    const save = screen.getByRole("button", { name: "Save Pro Edit settings" });
    expect(save).toBeDisabled();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    await user.click(toggle);
    expect(screen.getByRole("status")).toHaveTextContent(
      "No variant is made while heavy edits are not allowed",
    );
    await user.selectOptions(
      screen.getByLabelText("Heavy edits allowed (allow_heavy_edits)"),
      "true",
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    await user.selectOptions(
      screen.getByLabelText("Pro Edit preset"),
      "skull_moment",
    );
    await user.selectOptions(screen.getByLabelText("Maximum intensity"), "pro");
    await user.click(save);

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            url === "/api/campaigns/1/autopilot" && init?.method === "PUT",
        ),
      ).toBe(true),
    );
    const patch = fetchMock.mock.calls.find(
      ([url, init]) => url === "/api/campaigns/1" && init?.method === "PATCH",
    );
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({
      allow_heavy_edits: "true",
    });
    const put = fetchMock.mock.calls.find(
      ([url, init]) =>
        url === "/api/campaigns/1/autopilot" && init?.method === "PUT",
    );
    const kept: Partial<AutopilotSettings> = { ...SETTINGS };
    delete kept.campaign_id;
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({
      ...kept,
      proedit_enabled: true,
      proedit_preset: "skull_moment",
      proedit_max_intensity: "pro",
    });
  });

  it("does not touch the campaign when only the autopilot values change", async () => {
    const user = userEvent.setup();
    const fetchMock = api();
    renderSection();

    await user.click(
      await screen.findByRole("switch", {
        name: "Also make a Pro Edit variant",
      }),
    );
    await user.click(
      screen.getByRole("button", { name: "Save Pro Edit settings" }),
    );

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([, init]) => init?.method === "PUT"),
      ).toBe(true),
    );
    expect(
      fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH"),
    ).toBe(false);
  });

  it("shows nothing while Pro Edit is off", async () => {
    const fetchMock = api(false);
    renderSection();

    await waitFor(() =>
      expect(fetchMock.mock.calls.map(([url]) => url)).toContain(
        "/api/proedit/status",
      ),
    );
    expect(screen.queryByRole("region", { name: "Pro Edit" })).toBeNull();
    expect(
      screen.queryByRole("switch", { name: "Also make a Pro Edit variant" }),
    ).toBeNull();
  });
});
