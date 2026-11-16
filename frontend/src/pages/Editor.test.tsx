import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import { AppRoutes } from "@/routes";
import {
  mockLayoutAndMedia,
  renderEditor,
  stat,
  video,
} from "@/testing/editor";
import { failingCheck } from "@/testing/campaignFixtures";
import { json, mockRoutes } from "@/testing/mockApi";

beforeEach(mockLayoutAndMedia);

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("clip editor", () => {
  it("is full screen with the clip, its preview and a way back", async () => {
    renderEditor();

    expect(
      await screen.findByRole("heading", { name: "Pizza night" }),
    ).toBeVisible();
    expect(screen.queryByRole("navigation", { name: "Main navigation" })).toBe(
      null,
    );
    expect(screen.getByRole("link", { name: "Back to clips" })).toHaveAttribute(
      "href",
      "/projects/1",
    );
    expect(video().getAttribute("src")).toMatch(
      /^\/api\/clips\/7\/preview\?v=[0-9a-z]+$/,
    );
    expect(stat("In")).toBe("00:10.00");
    expect(stat("Out")).toBe("00:40.00");
    expect(stat("Length")).toBe("00:25.00");
    expect(screen.getByLabelText("Clip length")).toHaveTextContent("00:25.00");
    expect(screen.getByTitle("Cut 00:20.00 - 00:25.00")).toBeInTheDocument();
  });

  it("plays and pauses the preview", async () => {
    const user = userEvent.setup();
    renderEditor();
    await user.click(await screen.findByRole("button", { name: "Play" }));
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Pause" }));
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Play" })).toBeVisible();
  });

  it("drags the end handle to trim or extend the clip", async () => {
    renderEditor();
    const end = await screen.findByRole("slider", { name: "Clip end" });

    fireEvent.pointerDown(end, { button: 0, clientX: 450, pointerId: 1 });
    expect(end).toHaveAttribute("aria-valuenow", "45");
    fireEvent.pointerMove(end, { clientX: 300, pointerId: 1 });
    fireEvent.pointerUp(end, { pointerId: 1 });
    fireEvent.pointerMove(end, { clientX: 600, pointerId: 1 });

    expect(end).toHaveAttribute("aria-valuenow", "30");
    expect(stat("Out")).toBe("00:30.00");
    expect(stat("Length")).toBe("00:15.00");
  });

  it("moves a handle with the keyboard, keeping 1 s of clip", async () => {
    const user = userEvent.setup();
    renderEditor();
    const start = await screen.findByRole("slider", { name: "Clip start" });

    start.focus();
    await user.keyboard("{ArrowRight}");
    expect(start).toHaveAttribute("aria-valuenow", "10.1");
    await user.keyboard("{Shift>}{ArrowLeft}{/Shift}");
    expect(start).toHaveAttribute("aria-valuenow", "9.1");
    await user.keyboard("{Home}");
    expect(start).toHaveAttribute("aria-valuenow", "0");
    await user.keyboard("{End}");
    expect(start).toHaveAttribute("aria-valuenow", "39");
    expect(screen.queryByTitle(/^Cut /)).toBe(null);
    expect(stat("Cuts")).toBe("0");
  });

  it("maps the preview time to the source across cuts, and seeks", async () => {
    renderEditor();
    await screen.findByRole("heading", { name: "Pizza night" });

    video().currentTime = 12;
    fireEvent.timeUpdate(video());
    expect(screen.getByLabelText("Current time")).toHaveTextContent("00:12.00");
    // 12 s into the preview is source 27 s (the 5 s cut at 20 s skipped).
    expect(screen.getByTestId("playhead").style.left).toBe("45%");

    fireEvent.pointerDown(screen.getByLabelText("Timeline"), {
      button: 0,
      clientX: 300,
      pointerId: 1,
    });
    expect(video().currentTime).toBe(15);
    expect(screen.getByLabelText("Current time")).toHaveTextContent("00:15.00");
  });

  it("shows the score breakdown from the rail", async () => {
    const user = userEvent.setup();
    renderEditor();
    await user.click(await screen.findByRole("button", { name: "Score" }));

    const panel = screen.getByRole("complementary", { name: "Score panel" });
    expect(within(panel).getByText("85")).toBeVisible();
    expect(within(panel).getByRole("meter", { name: "Hook" })).toHaveAttribute(
      "aria-valuenow",
      "90",
    );
  });

  it("shows the campaign rule check from the rail", async () => {
    const user = userEvent.setup();
    renderEditor(undefined, undefined, {
      "GET /api/clips/7/campaign-check": () => json(failingCheck()),
    });
    await user.click(await screen.findByRole("button", { name: "Rules" }));

    const panel = screen.getByRole("complementary", { name: "Rules panel" });
    expect(
      await within(panel).findByRole("listitem", {
        name: "Required hashtags: fail",
      }),
    ).toBeVisible();
  });

  it("says so when the clip does not exist", async () => {
    mockRoutes({});
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter initialEntries={["/clips/99"]}>
          <AppRoutes />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Could not load this clip.")).toBeVisible();
  });
});
