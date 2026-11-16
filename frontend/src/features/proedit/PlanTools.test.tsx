import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EdlItem, ProEditRun } from "@/api/types";
import { mockEventSource } from "@/testing/fakeEventSource";
import { CLIP, mockLayoutAndMedia, renderAt } from "@/testing/editor";
import { callsTo, json, type Handler } from "@/testing/mockApi";
import {
  criticRun,
  PLAN,
  PLAN_V2,
  proEditRun,
  TIMING,
} from "@/testing/proeditFixtures";

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
const DONE: ProEditRun = {
  ...proEditRun(),
  status: "done",
  plan_id: 40,
  finished_at: "2026-05-01T10:00:00",
};

/** Open the Pro Edit page of clip 7: variant 12 with plan versions v1, v2
 * (current) and the given runs. */
function open(routes: Record<string, Handler> = {}, runs = [DONE]) {
  return renderAt("/clips/7/proedit", {
    "GET /api/proedit/status": () =>
      json({ enabled: true, critic_max_rounds: 2 }),
    "GET /api/proedit/clips/7/variants": () => json([VARIANT]),
    "GET /api/clips/12": () => json(VARIANT),
    [`GET ${API}/plan`]: () => json(PLAN_V2),
    [`GET ${API}/plans`]: () => json([PLAN, PLAN_V2]),
    [`GET ${API}/timing`]: () => json(TIMING),
    [`GET ${API}/runs`]: () => json(runs),
    ...routes,
  });
}

describe("Pro Edit plan tools", () => {
  it("shows the inspector of the selected item and stores its params", async () => {
    const user = userEvent.setup();
    const fetchMock = open({
      [`PATCH ${API}/plan`]: (_url, init) =>
        json({
          ...PLAN_V2,
          id: 42,
          version: 3,
          items: (JSON.parse(String(init?.body)) as { items: EdlItem[] }).items,
        }),
    });

    expect(
      await screen.findByText("Select an item to change its parameters."),
    ).toBeInTheDocument();
    const zoom = within(
      await screen.findByRole("group", { name: "Zoom lane" }),
    ).getByRole("button");
    act(() => zoom.focus());
    const inspector = screen.getByRole("region", { name: "Inspector" });
    expect(within(inspector).getByLabelText("scale")).toHaveValue(1.3);
    await user.clear(within(inspector).getByLabelText("scale"));
    await user.type(within(inspector).getByLabelText("scale"), "1.15");
    await user.click(within(inspector).getByRole("button", { name: "Apply" }));

    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", `${API}/plan`)).toHaveLength(1),
    );
    const sent = JSON.parse(
      String(callsTo(fetchMock, "PATCH", `${API}/plan`)[0][1]?.body),
    ) as { items: EdlItem[] };
    expect(sent.items[0].params).toMatchObject({ scale: 1.15 });
    expect(sent.items[1]).toEqual(PLAN_V2.items[1]);
    expect(await screen.findByText("Plan v3")).toBeInTheDocument();
  });

  it("lists the plan versions and diffs the chosen one", async () => {
    const user = userEvent.setup();
    open();

    const versions = await screen.findByRole("region", {
      name: "Version history",
    });
    const diff = await within(versions).findByRole("list", {
      name: "Changes from v1",
    });
    expect(diff).toHaveTextContent("Changed Zoom punch #1");
    expect(diff).toHaveTextContent("scale unset → 1.3");
    expect(diff).toHaveTextContent("Added Flash #3");
    expect(diff).toHaveTextContent("Removed SFX #2");
    expect(versions).toHaveTextContent("v2 · Critic · 2 items");

    await user.click(within(versions).getByRole("button", { name: /^v1/ }));
    expect(versions).toHaveTextContent("The first version has 2 items.");
  });

  it("shows the critic's scores and what it changed", async () => {
    open({}, [criticRun()]);

    const critic = await screen.findByRole("region", { name: "Critic" });
    const first = within(critic).getByRole("region", {
      name: "Critic round 1",
    });
    expect(first).toHaveTextContent("Hook strength");
    expect(first).toHaveTextContent("4/10");
    expect(first).toHaveTextContent("The hook is flat.");
    expect(
      within(first).getByRole("list", { name: "What changed" }),
    ).toHaveTextContent("Modified Zoom punch #1Land the punch on the word.");
    expect(first).toHaveTextContent("Not applied: item 9 does not exist");
    expect(critic).toHaveTextContent("Every score passed.");
    expect(
      within(
        within(critic).getByRole("region", { name: "Critic round 2" }),
      ).getByText("8/10"),
    ).toBeInTheDocument();
  });

  it("lists what post-processing moved or dropped, apart from the critic", async () => {
    const notes = [
      "Moved sfx at 10.20 s: it covered the punchline word at 10.23 s",
      "Left out skull_moment at 16.37 s: its overlay did not fit: no room",
      "Every score passed.",
    ];
    open({}, [{ ...criticRun(), notes }]);

    const edits = await screen.findByRole("region", { name: "Edit notes" });
    const lines = within(edits).getAllByRole("listitem");
    expect(lines.map((line) => line.textContent)).toEqual([
      "MovedSFX10.20 sit covered the punchline word at 10.23 s",
      "Left outSkull moment16.37 sits overlay did not fit: no room",
    ]);
    const critic = screen.getByRole("region", { name: "Critic" });
    expect(critic).not.toHaveTextContent("punchline word");
    expect(critic).toHaveTextContent("Every score passed.");
  });

  it("says when every planned move was kept", async () => {
    open();

    const edits = await screen.findByRole("region", { name: "Edit notes" });
    expect(edits).toHaveTextContent("Every planned move was kept.");
  });

  it("says when the critic has not run", async () => {
    open();

    expect(
      await screen.findByText("The critic has not scored this variant yet."),
    ).toBeInTheDocument();
  });

  it("queues the Director and the critic", async () => {
    const user = userEvent.setup();
    const queued = () => json({ clip: VARIANT, run: DONE, job_id: 77 }, 202);
    const fetchMock = open({
      [`POST ${API}/regenerate`]: queued,
      [`POST ${API}/critic`]: queued,
    });

    await user.click(
      await screen.findByRole("button", { name: "Regenerate with Director" }),
    );
    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", `${API}/regenerate`)).toHaveLength(1),
    );
    await user.click(screen.getByRole("button", { name: "Run critic again" }));
    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", `${API}/critic`)).toHaveLength(1),
    );
  });

  it("resets to plan v1 as the next version", async () => {
    const user = userEvent.setup();
    const fetchMock = open({
      [`POST ${API}/reset`]: () =>
        json({ ...PLAN, id: 43, version: 3, created_by: "user" }),
    });

    await user.click(
      await screen.findByRole("button", { name: "Reset to plan v1" }),
    );

    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", `${API}/reset`)).toHaveLength(1),
    );
    expect(await screen.findByText("Plan v3")).toBeInTheDocument();
  });

  it("explains a refused request", async () => {
    const user = userEvent.setup();
    open({
      [`POST ${API}/critic`]: () =>
        json(
          {
            error: "usage_cap",
            message: "the monthly Pro Edit cap is used up",
          },
          409,
        ),
    });

    await user.click(
      await screen.findByRole("button", { name: "Run critic again" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "the monthly Pro Edit cap is used up",
    );
  });

  it("locks the actions while a job runs and without critic rounds", async () => {
    open(
      {
        "GET /api/proedit/status": () =>
          json({ enabled: true, critic_max_rounds: 0 }),
      },
      [{ ...DONE, status: "running", plan_id: null }],
    );

    const regenerate = await screen.findByRole("button", {
      name: "Regenerate with Director",
    });
    await waitFor(() => expect(regenerate).toBeDisabled());
    expect(
      screen.getByRole("button", { name: "Run critic again" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Reset to plan v1" }),
    ).toBeDisabled();
  });
});
