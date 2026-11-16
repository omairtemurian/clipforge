import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import { campaign } from "@/testing/campaignFixtures";
import { callsTo, json, mockRoutes, project } from "@/testing/mockApi";
import { ProjectCampaignSelect } from "./ProjectCampaignSelect";

afterEach(() => vi.unstubAllGlobals());

function renderSelect(campaignId: number | null) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <ProjectCampaignSelect
          project={project({ id: 1, campaign_id: campaignId })}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("project campaign select", () => {
  it("applies the chosen campaign to the project", async () => {
    const user = userEvent.setup();
    const fetchMock = mockRoutes({
      "GET /api/campaigns": () =>
        json([campaign(), campaign({ id: 2, name: "Direct deal" })]),
      "PUT /api/projects/1/campaign": () => json(project({ campaign_id: 2 })),
    });
    renderSelect(null);

    const select = await screen.findByLabelText("Campaign");
    await waitFor(() => expect(select).toBeEnabled());
    await user.selectOptions(select, "Direct deal");

    await waitFor(() =>
      expect(
        callsTo(fetchMock, "PUT", "/api/projects/1/campaign"),
      ).toHaveLength(1),
    );
    expect(
      JSON.parse(
        String(
          callsTo(fetchMock, "PUT", "/api/projects/1/campaign")[0][1]?.body,
        ),
      ),
    ).toEqual({ campaign_id: 2 });
  });

  it("leaves the campaign with the empty choice", async () => {
    const user = userEvent.setup();
    const fetchMock = mockRoutes({
      "GET /api/campaigns": () => json([campaign()]),
      "PUT /api/projects/1/campaign": () =>
        json(project({ campaign_id: null })),
    });
    renderSelect(1);

    const select = await screen.findByLabelText("Campaign");
    await waitFor(() => expect(select).toBeEnabled());
    expect(select).toHaveValue("1");
    await user.selectOptions(select, "No campaign");

    await waitFor(() =>
      expect(
        JSON.parse(
          String(
            callsTo(fetchMock, "PUT", "/api/projects/1/campaign")[0][1]?.body,
          ),
        ),
      ).toEqual({ campaign_id: null }),
    );
  });

  it("points to the Campaigns page when there is none", async () => {
    mockRoutes({ "GET /api/campaigns": () => json([]) });
    renderSelect(null);

    expect(
      await screen.findByRole("link", { name: "Add it under Campaigns" }),
    ).toHaveAttribute("href", "/campaigns");
  });
});
