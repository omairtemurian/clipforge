import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Clip, ZoomKeyframe } from "@/api/types";
import { CLIP, mockLayoutAndMedia, renderEditor } from "@/testing/editor";
import { callsTo, json } from "@/testing/mockApi";

beforeEach(mockLayoutAndMedia);

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const AUTO_ZOOMS: ZoomKeyframe[] = [
  { t: 12, scale: 1 },
  { t: 12.2, scale: 1.15 },
  { t: 14.2, scale: 1.15 },
  { t: 14.7, scale: 1 },
  { t: 20, scale: 1 },
  { t: 20.2, scale: 1.12 },
  { t: 22.2, scale: 1.12 },
  { t: 22.7, scale: 1 },
];

async function openLayout(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Layout" }));
  return screen.getByRole("complementary", { name: "Layout panel" });
}

function patchBody(fetchMock: ReturnType<typeof renderEditor>, index = 0) {
  return JSON.parse(
    String(callsTo(fetchMock, "PATCH", "/api/clips/7")[index][1]?.body),
  );
}

describe("auto zoom", () => {
  it("turns the punch-ins on, then off, and saves the switch", async () => {
    const user = userEvent.setup();
    const fetchMock = renderEditor(undefined, undefined, {
      "GET /api/clips/7/auto-zooms?start=10&end=40": () => json(AUTO_ZOOMS),
      "PATCH /api/clips/7": (_url, init) =>
        json({ ...CLIP, ...JSON.parse(String(init?.body)) } satisfies Clip),
    });
    const panel = await openLayout(user);
    const toggle = within(panel).getByRole("switch", { name: "Auto zoom" });
    expect(toggle).not.toBeChecked();
    await waitFor(() => expect(toggle).toBeEnabled());
    expect(
      within(panel).getByText(/new sentences and laughs \(2 in this clip\)/),
    ).toBeVisible();

    await user.click(toggle);
    expect(toggle).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/clips/7")).toHaveLength(1),
    );
    expect(patchBody(fetchMock)).toMatchObject({
      auto_zoom: true,
      zoom_keyframes: AUTO_ZOOMS,
    });

    await user.click(toggle);
    expect(toggle).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/clips/7")).toHaveLength(2),
    );
    expect(patchBody(fetchMock, 1)).toMatchObject({
      auto_zoom: false,
      zoom_keyframes: AUTO_ZOOMS,
    });
  });

  it("stays off when the punch-ins cannot be found", async () => {
    const user = userEvent.setup();
    renderEditor(undefined, undefined, {
      "GET /api/clips/7/auto-zooms?start=10&end=40": () =>
        json({ error: "conflict", message: "no signals.json" }, 409),
    });
    const panel = await openLayout(user);

    expect(
      await within(panel).findByText(
        "The punch-ins of this clip could not be found.",
      ),
    ).toBeVisible();
    expect(
      within(panel).getByRole("switch", { name: "Auto zoom" }),
    ).toBeDisabled();
  });
});
