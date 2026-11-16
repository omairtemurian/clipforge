import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ProEditPlan } from "@/api/types";
import { mockEventSource } from "@/testing/fakeEventSource";
import { CLIP, mockLayoutAndMedia, renderAt } from "@/testing/editor";
import { callsTo, json, type Handler } from "@/testing/mockApi";
import { PLAN, TIMING } from "@/testing/proeditFixtures";
import { MATCH } from "@/testing/styleRecipeFixtures";

beforeEach(() => {
  mockLayoutAndMedia();
  mockEventSource();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const VARIANT = {
  ...CLIP,
  id: 12,
  title: "Pizza night — Pro Edit",
  parent_clip_id: 7,
  variant: "pro_edit" as const,
  status: "rendered" as const,
  output_path: "/out/12.mp4",
};
const API = "/api/proedit/clips/12";

/** Open the Pro Edit page of clip 7 with variant 12 on plan. */
function open(plan: ProEditPlan, routes: Record<string, Handler> = {}) {
  return renderAt("/clips/7/proedit", {
    "GET /api/proedit/status": () => json({ enabled: true }),
    "GET /api/proedit/clips/7/variants": () => json([VARIANT]),
    "GET /api/clips/12": () => json(VARIANT),
    [`GET ${API}/plan`]: () => json(plan),
    [`GET ${API}/plans`]: () => json([plan]),
    [`GET ${API}/timing`]: () => json(TIMING),
    [`GET ${API}/runs`]: () => json([]),
    ...routes,
  });
}

describe("Style match panel", () => {
  it("measures the variant against its plan's recipe", async () => {
    const user = userEvent.setup();
    const fetchMock = open(
      { ...PLAN, style_recipe_id: 3 },
      {
        [`GET ${API}/style-match`]: () => json(null),
        [`POST ${API}/style-match`]: () => json(MATCH),
      },
    );

    const panel = await screen.findByRole("region", { name: "Style match" });
    expect(
      await within(panel).findByText(/Measure the rendered video/),
    ).toBeInTheDocument();
    await user.click(within(panel).getByRole("button", { name: "Measure" }));

    await waitFor(() => expect(panel).toHaveTextContent("75/100"));
    expect(callsTo(fetchMock, "POST", `${API}/style-match`)).toHaveLength(1);
    expect(
      within(panel).getByRole("link", { name: "Night phonk" }),
    ).toHaveAttribute("href", "/proedit/style-recipes?recipe=3");
    const rows = within(
      within(panel).getByRole("list", { name: "Style metrics" }),
    ).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Brightness50%");
    expect(rows[0]).toHaveTextContent("60% · target 30% (24% to 36%)");
    expect(rows[1]).toHaveTextContent("Cuts100%");
  });

  it("shows the last measured match", async () => {
    open(
      { ...PLAN, style_recipe_id: 3 },
      { [`GET ${API}/style-match`]: () => json(MATCH) },
    );

    const panel = await screen.findByRole("region", { name: "Style match" });
    await waitFor(() => expect(panel).toHaveTextContent("75/100"));
  });

  it("is not shown without a style recipe", async () => {
    const fetchMock = open(PLAN);

    expect(
      await screen.findByRole("region", { name: "Critic" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Style match" })).toBeNull();
    expect(callsTo(fetchMock, "GET", `${API}/style-match`)).toHaveLength(0);
  });
});
