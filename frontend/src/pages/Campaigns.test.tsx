import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { Campaign } from "@/api/types";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import { campaign } from "@/testing/campaignFixtures";
import {
  callsTo,
  captionTemplate,
  json,
  mockRoutes,
  type Handler,
} from "@/testing/mockApi";
import { CampaignsPage } from "./CampaignsPage";

afterEach(() => {
  vi.unstubAllGlobals();
  act(() => clearToasts());
});

function api(initial: Campaign[], extra: Record<string, Handler> = {}) {
  let current = initial;
  return mockRoutes({
    "GET /api/campaigns": () => json(current),
    "GET /api/submissions?campaign_id=1": () => json([]),
    "GET /api/caption-templates": () =>
      json(["karaoke_bold", "minimal"].map(captionTemplate)),
    "POST /api/campaigns": (_url, init) => {
      const body = JSON.parse(String(init?.body)) as Partial<Campaign>;
      const saved = campaign({ id: 2, ...body });
      current = [...current, saved];
      return json(saved, 201);
    },
    ...extra,
  });
}

function renderPage() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <CampaignsPage />
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("Campaigns page", () => {
  it("creates a campaign from typed and pasted entries", async () => {
    const user = userEvent.setup();
    const fetchMock = api([]);
    renderPage();

    const form = await screen.findByRole("form", { name: "New campaign" });
    await user.type(within(form).getByLabelText("Name"), "  Whop clips ");
    await user.type(
      within(form).getByLabelText("Creator channel links"),
      "https://www.youtube.com/@afro",
    );
    await user.click(within(form).getByRole("checkbox", { name: "TikTok" }));
    await user.type(
      within(form).getByLabelText("Required hashtags"),
      "#afro, #clips #afro",
    );
    await user.type(
      within(form).getByLabelText("Required credit line"),
      "Clip from Afro",
    );
    await user.type(within(form).getByLabelText("Minimum length (s)"), "20");
    await user.selectOptions(
      within(form).getByLabelText("Caption template"),
      "minimal",
    );
    await user.click(
      within(form).getByRole("button", { name: "Create campaign" }),
    );

    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", "/api/campaigns")).toHaveLength(1),
    );
    const body = JSON.parse(
      String(callsTo(fetchMock, "POST", "/api/campaigns")[0][1]?.body),
    ) as Campaign;
    expect(body).toMatchObject({
      name: "Whop clips",
      source_channel_urls: ["https://www.youtube.com/@afro"],
      allowed_platforms: ["tiktok"],
      required_hashtags: ["afro", "clips", "afro"],
      required_credit_line: "Clip from Afro",
      min_duration_s: 20,
      caption_template: "minimal",
    });
    expect(await screen.findByText('Saved "Whop clips".')).toBeVisible();
    expect(
      await screen.findByRole("form", { name: "Edit Whop clips" }),
    ).toBeVisible();
  });

  it("shows problems and sends nothing until the entries are fine", async () => {
    const user = userEvent.setup();
    const fetchMock = api([]);
    renderPage();

    const form = await screen.findByRole("form", { name: "New campaign" });
    await user.type(within(form).getByLabelText("Minimum length (s)"), "50");
    await user.type(within(form).getByLabelText("Maximum length (s)"), "20");
    await user.click(
      within(form).getByRole("button", { name: "Create campaign" }),
    );

    expect(within(form).getByText("Give the campaign a name.")).toBeVisible();
    expect(
      within(form).getByText("The minimum must not be over the maximum."),
    ).toBeVisible();
    expect(callsTo(fetchMock, "POST", "/api/campaigns")).toHaveLength(0);
  });

  it("uploads the permission screenshot and shows the evidence state", async () => {
    const user = userEvent.setup();
    const saved = campaign({ permission_source_url: "https://a.test/ok" });
    const complete = campaign({
      permission_source_url: "https://a.test/ok",
      permission_screenshot_asset_id: 9,
      permission_checked_at: "2026-11-01T10:00:00",
      permission_complete: true,
    });
    const fetchMock = api([saved], {
      "GET /api/campaigns/1": () => json(saved),
      "POST /api/campaigns/1/permission-screenshot": () => json(complete),
    });
    renderPage();

    const form = await screen.findByRole("form", { name: "Edit Whop clips" });
    expect(
      within(form).getByText(/Incomplete: publishing is blocked/),
    ).toBeVisible();
    const file = new File(["png"], "proof.png", { type: "image/png" });
    await user.upload(
      within(form).getByLabelText("Permission screenshot"),
      file,
    );
    await user.click(
      within(form).getByRole("button", { name: "Save changes" }),
    );

    await waitFor(() =>
      expect(
        callsTo(fetchMock, "POST", "/api/campaigns/1/permission-screenshot"),
      ).toHaveLength(1),
    );
    expect(callsTo(fetchMock, "PATCH", "/api/campaigns/1")).toHaveLength(0);
    const sent = callsTo(
      fetchMock,
      "POST",
      "/api/campaigns/1/permission-screenshot",
    )[0][1]?.body as FormData;
    expect((sent.get("file") as File).name).toBe("proof.png");
  });

  it("changes only what was edited and deletes after a confirmation", async () => {
    const user = userEvent.setup();
    let current = [campaign()];
    const fetchMock = api(current, {
      "GET /api/campaigns": () => json(current),
      "PATCH /api/campaigns/1": (_url, init) => {
        current = [campaign({ ...JSON.parse(String(init?.body)) })];
        return json(current[0]);
      },
      "DELETE /api/campaigns/1": () => {
        current = [];
        return new Response(null, { status: 204 });
      },
    });
    renderPage();

    const form = await screen.findByRole("form", { name: "Edit Whop clips" });
    await user.clear(within(form).getByLabelText("Name"));
    await user.type(within(form).getByLabelText("Name"), "Renamed");
    await user.click(
      within(form).getByRole("button", { name: "Save changes" }),
    );

    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/campaigns/1")).toHaveLength(1),
    );
    expect(
      JSON.parse(
        String(callsTo(fetchMock, "PATCH", "/api/campaigns/1")[0][1]?.body),
      ),
    ).toEqual({ name: "Renamed" });

    const edited = await screen.findByRole("form", { name: "Edit Renamed" });
    await user.click(within(edited).getByRole("button", { name: "Delete" }));
    expect(callsTo(fetchMock, "DELETE", "/api/campaigns/1")).toHaveLength(0);
    await user.click(
      within(edited).getByRole("button", { name: "Confirm delete" }),
    );

    expect(
      await screen.findByRole("form", { name: "New campaign" }),
    ).toBeVisible();
    expect(callsTo(fetchMock, "DELETE", "/api/campaigns/1")).toHaveLength(1);
  });
});
