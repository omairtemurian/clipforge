import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Clip } from "@/api/types";
import { CLIP, mockLayoutAndMedia, renderEditor, stat } from "@/testing/editor";
import { callsTo, json } from "@/testing/mockApi";

beforeEach(mockLayoutAndMedia);

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const AUTO_CUTS = [
  [12, 13],
  [22, 24],
  [30, 31],
];

function renderWithAutoCuts() {
  return renderEditor(undefined, undefined, {
    "GET /api/clips/7/auto-cuts?start=10&end=40": () => json(AUTO_CUTS),
    "PATCH /api/clips/7": (_url, init) =>
      json({ ...CLIP, ...JSON.parse(String(init?.body)) } satisfies Clip),
  });
}

async function openLayout(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Layout" }));
  return screen.getByRole("complementary", { name: "Layout panel" });
}

describe("auto cut", () => {
  it("cuts the silences, brings them back and saves the switch", async () => {
    const user = userEvent.setup();
    const fetchMock = renderWithAutoCuts();
    const panel = await openLayout(user);
    const toggle = within(panel).getByRole("switch", {
      name: "Auto cut silences",
    });
    expect(toggle).not.toBeChecked();
    await waitFor(() => expect(toggle).toBeEnabled());
    expect(
      within(panel).getByText(/pauses between sentences \(3 in this clip\)/),
    ).toBeVisible();
    expect(stat("Cuts")).toBe("1");

    await user.click(toggle);
    expect(toggle).toBeChecked();
    // 20-25 (the user's) holds 22-24; 12-13 and 30-31 are new.
    expect(stat("Cuts")).toBe("3");

    await user.click(toggle);
    // Off takes out what auto cut covers: 20-25 keeps 20-22 and 24-25.
    expect(stat("Cuts")).toBe("2");
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(toggle).toBeChecked();
    expect(stat("Cuts")).toBe("3");

    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/clips/7")).toHaveLength(1),
    );
    const body = JSON.parse(
      String(callsTo(fetchMock, "PATCH", "/api/clips/7")[0][1]?.body),
    );
    expect(body).toMatchObject({
      auto_cut: true,
      cut_ranges: [
        [12, 13],
        [20, 25],
        [30, 31],
      ],
    });
  });

  it("stays off when the silences cannot be found", async () => {
    const user = userEvent.setup();
    renderEditor(undefined, undefined, {
      "GET /api/clips/7/auto-cuts?start=10&end=40": () =>
        json({ error: "conflict", message: "no signals.json" }, 409),
    });
    const panel = await openLayout(user);

    expect(
      await within(panel).findByText(
        "The silences of this clip could not be found.",
      ),
    ).toBeVisible();
    expect(
      within(panel).getByRole("switch", { name: "Auto cut silences" }),
    ).toBeDisabled();
  });
});
