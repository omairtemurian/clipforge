import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EdlItem, ProEditRun } from "@/api/types";
import { mockEventSource } from "@/testing/fakeEventSource";
import { CLIP, mockLayoutAndMedia, renderAt } from "@/testing/editor";
import { callsTo, json, type Handler } from "@/testing/mockApi";
import { PLAN, proEditRun, TIMING } from "@/testing/proeditFixtures";

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
const PLAN_URL = "/api/proedit/clips/12/plan";

/** A run of variant 12 with status, done with plan 40 by default. */
function run(overrides: Partial<ProEditRun> = {}): ProEditRun {
  return {
    ...proEditRun(),
    status: "done",
    plan_id: 40,
    finished_at: "2026-05-01T10:00:00",
    ...overrides,
  };
}

/** Open the Pro Edit page of clip 7 with variant 12, its plan and runs. */
function open(routes: Record<string, Handler> = {}, runs = [run()]) {
  return renderAt("/clips/7/proedit", {
    "GET /api/proedit/status": () => json({ enabled: true }),
    "GET /api/proedit/clips/7/variants": () => json([VARIANT]),
    "GET /api/clips/12": () => json(VARIANT),
    "GET /api/proedit/clips/12/plan": () => json(PLAN),
    "GET /api/proedit/clips/12/timing": () => json(TIMING),
    "GET /api/proedit/clips/12/runs": () => json(runs),
    ...routes,
  });
}

/** The items sent by the nth PATCH of the plan. */
function patched(fetchMock: ReturnType<typeof open>, n = 0): EdlItem[] {
  const init = callsTo(fetchMock, "PATCH", PLAN_URL)[n][1];
  return (JSON.parse(String(init?.body)) as { items: EdlItem[] }).items;
}

const saved = (items: EdlItem[]) => () =>
  json({ ...PLAN, id: 41, version: 2, items });

describe("Pro Edit editor", () => {
  it("shows both previews and the plan's items on their lanes", async () => {
    open();

    const zoom = within(
      await screen.findByRole("group", { name: "Zoom lane" }),
    ).getByRole("button", { name: /Zoom punch/ });
    expect(zoom).toHaveAccessibleName(/Why: punch on the hook/);
    expect(
      within(screen.getByRole("group", { name: "SFX lane" })).getByRole(
        "button",
      ),
    ).toHaveAccessibleName(/whoosh into the reveal/);
    expect(screen.getAllByTestId("beat-mark")).toHaveLength(6);
    expect(screen.getByLabelText("Plan version")).toHaveTextContent("Plan v1");
    expect(screen.getByLabelText("Pro Edit preview")).toHaveAttribute(
      "src",
      expect.stringContaining("/api/proedit/clips/12/video?v="),
    );
    expect(screen.getByLabelText("Original preview")).toHaveProperty(
      "muted",
      true,
    );
  });

  it("snaps a dragged item to a beat and stores it as the next version", async () => {
    const fetchMock = open({
      [`PATCH ${PLAN_URL}`]: (_url, init) =>
        saved((JSON.parse(String(init?.body)) as { items: EdlItem[] }).items)(),
    });
    const zoom = within(
      await screen.findByRole("group", { name: "Zoom lane" }),
    ).getByRole("button");

    // 600 px for 10 s: grab at 2.1667 s, drop near 3.1 s (start ≈ 2.93 s).
    fireEvent.pointerDown(zoom, { button: 0, clientX: 130 });
    fireEvent.pointerMove(zoom, { clientX: 186 });
    expect(screen.getByRole("status")).toHaveTextContent("Snaps to beat at");
    expect(screen.getByTestId("snap-guide")).toBeInTheDocument();
    fireEvent.pointerUp(zoom);

    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", PLAN_URL)).toHaveLength(1),
    );
    const [moved, whoosh] = patched(fetchMock);
    expect(moved.t_start).toBeCloseTo(3);
    expect(moved.t_end).toBeCloseTo(3.5);
    expect(whoosh).toEqual(PLAN.items[1]);
    expect(await screen.findByText("Plan v2")).toBeInTheDocument();
  });

  it("nudges the focused item a frame with the arrow keys", async () => {
    const user = userEvent.setup();
    const fetchMock = open({
      [`PATCH ${PLAN_URL}`]: saved(PLAN.items),
    });
    const sfx = within(
      await screen.findByRole("group", { name: "SFX lane" }),
    ).getByRole("button");

    act(() => sfx.focus());
    expect(screen.getByLabelText("Selected item")).toHaveTextContent(
      "Why: whoosh into the reveal",
    );
    await user.keyboard("{ArrowRight}");

    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", PLAN_URL)).toHaveLength(1),
    );
    expect(patched(fetchMock)[1].t_start * 30).toBeCloseTo(151);
  });

  it("puts a refused edit back and says why", async () => {
    const user = userEvent.setup();
    open({
      [`PATCH ${PLAN_URL}`]: () =>
        json(
          {
            error: "invalid_plan",
            message: "the plan is not valid: item 2 overlaps item 3",
          },
          422,
        ),
    });
    const sfx = within(
      await screen.findByRole("group", { name: "SFX lane" }),
    ).getByRole("button");

    act(() => sfx.focus());
    await user.keyboard("{Shift>}{ArrowLeft}{/Shift}");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "item 2 overlaps item 3",
    );
    expect(sfx).toHaveAccessibleName(/00:05\.00 - 00:05\.50/);
    expect(screen.getByLabelText("Plan version")).toHaveTextContent("Plan v1");
  });

  it("locks the lanes while a job of the variant runs", async () => {
    const user = userEvent.setup();
    const fetchMock = open({}, [run({ status: "running", plan_id: null })]);
    const zoom = within(
      await screen.findByRole("group", { name: "Zoom lane" }),
    ).getByRole("button");

    await waitFor(() =>
      expect(screen.getByLabelText("Plan version")).toHaveTextContent(
        "a job is running",
      ),
    );
    expect(zoom).toHaveAttribute("aria-disabled", "true");
    expect(screen.queryByTestId("edl-item-start")).not.toBeInTheDocument();
    act(() => zoom.focus());
    await user.keyboard("{ArrowRight}");
    expect(callsTo(fetchMock, "PATCH", PLAN_URL)).toHaveLength(0);
  });

  it("offers to render an edited plan", async () => {
    const user = userEvent.setup();
    const fetchMock = open(
      {
        "GET /api/proedit/clips/12/plan": () =>
          json({ ...PLAN, id: 41, version: 2 }),
        "POST /api/proedit/clips/12/render": () =>
          json({ clip: VARIANT, run: run({ status: "queued" }) }, 202),
      },
      [run()],
    );

    await user.click(
      await screen.findByRole("button", { name: "Render plan v2" }),
    );
    await waitFor(() =>
      expect(
        callsTo(fetchMock, "POST", "/api/proedit/clips/12/render"),
      ).toHaveLength(1),
    );
  });

  it("follows the render it queued: the runs load again", async () => {
    const user = userEvent.setup();
    let runs = [run()];
    open({
      "GET /api/proedit/clips/12/plan": () =>
        json({ ...PLAN, id: 41, version: 2 }),
      "GET /api/proedit/clips/12/runs": () => json(runs),
      "POST /api/proedit/clips/12/render": () => {
        // A fast render: done before the editor asks for the runs again.
        runs = [run({ id: 2, plan_id: 41, mode: "render" }), ...runs];
        return json({ clip: VARIANT, run: runs[0] }, 202);
      },
    });

    await user.click(
      await screen.findByRole("button", { name: "Render plan v2" }),
    );

    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Render plan v2" }),
      ).not.toBeInTheDocument(),
    );
  });
});
