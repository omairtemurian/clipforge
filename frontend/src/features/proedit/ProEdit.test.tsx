import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockEventSource } from "@/testing/fakeEventSource";
import {
  CLIP,
  mockLayoutAndMedia,
  renderAt,
  renderEditor,
} from "@/testing/editor";
import { callsTo, json } from "@/testing/mockApi";
import { CHOICES, PLAN, TIMING } from "@/testing/proeditFixtures";

beforeEach(() => {
  mockLayoutAndMedia();
  mockEventSource();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const ENABLED = { "GET /api/proedit/status": () => json({ enabled: true }) };
const DISABLED = {
  "GET /api/proedit/status": () =>
    json({ error: "proedit_disabled", message: "Pro Edit is turned off" }, 404),
};
const VARIANT = {
  ...CLIP,
  id: 12,
  title: "Pizza night — Pro Edit",
  parent_clip_id: 7,
  variant: "pro_edit" as const,
  status: "rendered" as const,
  output_path: "/out/12.mp4",
};

describe("Pro Edit entry", () => {
  it("opens the dialog from the editor, which links to the variants' editor", async () => {
    const user = userEvent.setup();
    renderEditor(undefined, undefined, {
      ...ENABLED,
      "GET /api/proedit/clips/7/choices": () => json(CHOICES),
      "GET /api/proedit/clips/7/variants": () => json([VARIANT]),
      "GET /api/clips/12": () => json(VARIANT),
      "GET /api/proedit/clips/12/plan": () => json(PLAN),
      "GET /api/proedit/clips/12/timing": () => json(TIMING),
      "GET /api/proedit/clips/12/runs": () => json([]),
    });

    await user.click(await screen.findByRole("button", { name: "Pro Edit" }));
    const dialog = await screen.findByRole("dialog", { name: "Pro Edit" });
    expect(await within(dialog).findAllByRole("radio")).toHaveLength(6);
    await user.click(
      within(dialog).getByRole("link", {
        name: "See this clip's Pro Edit variants",
      }),
    );

    expect(
      await screen.findByRole("heading", { name: "Pro Edit" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("region", { name: "EDL lanes" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Original preview")).toBeInTheDocument();
    expect(screen.getByLabelText("Pro Edit preview")).toBeInTheDocument();
  });

  it("hides the entry when Pro Edit is off", async () => {
    const fetchMock = renderEditor(undefined, undefined, DISABLED);

    await screen.findByRole("button", { name: /^Render/ });
    await waitFor(() =>
      expect(callsTo(fetchMock, "GET", "/api/proedit/status")).toHaveLength(1),
    );
    expect(
      screen.queryByRole("button", { name: "Pro Edit" }),
    ).not.toBeInTheDocument();
  });

  it("shows no entry on a Pro Edit variant", async () => {
    const fetchMock = renderEditor({ ...VARIANT, id: 7 }, undefined, ENABLED);

    await screen.findByRole("button", { name: /^Render/ });
    await waitFor(() =>
      expect(callsTo(fetchMock, "GET", "/api/proedit/status")).toHaveLength(1),
    );
    expect(
      screen.queryByRole("button", { name: "Pro Edit" }),
    ).not.toBeInTheDocument();
  });
});

describe("Pro Edit page", () => {
  it("says the clip has no variant yet", async () => {
    renderAt("/clips/7/proedit", {
      ...ENABLED,
      "GET /api/proedit/clips/7/variants": () => json([]),
    });

    expect(
      await screen.findByText("No Pro Edit variant yet"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Back to the clip" }),
    ).toHaveAttribute("href", "/clips/7");
  });

  it("goes to the original's page when opened on a variant", async () => {
    renderAt("/clips/12/proedit", {
      ...ENABLED,
      "GET /api/clips/12": () => json(VARIANT),
      "GET /api/proedit/clips/7/variants": () => json([VARIANT]),
      "GET /api/proedit/clips/12/plan": () => json(PLAN),
      "GET /api/proedit/clips/12/timing": () => json(TIMING),
      "GET /api/proedit/clips/12/runs": () => json([]),
    });

    expect(
      await screen.findByRole("region", { name: "EDL lanes" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Back to the clip" }),
    ).toHaveAttribute("href", "/clips/7");
  });

  it("goes to the clip's editor when Pro Edit is off", async () => {
    const fetchMock = renderAt("/clips/7/proedit", DISABLED);

    expect(
      await screen.findByRole("button", { name: /^Render/ }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Pro Edit" })).toBeNull();
    expect(
      callsTo(fetchMock, "GET", "/api/proedit/clips/7/variants"),
    ).toHaveLength(0);
  });
});
