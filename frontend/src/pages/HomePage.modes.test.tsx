import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { createQueryClient } from "@/api/queryClient";
import { DEFAULTS, json, mockRoutes } from "@/testing/mockApi";
import { HomePage } from "./HomePage";

const CAPTIONS_CHIP = "Captions only (no clipping — whole video as one clip)";

const TOKEN = "d".repeat(32);

function renderHome() {
  mockRoutes({
    "GET /api/projects": () => json([]),
    "GET /api/processing-defaults": () => json(DEFAULTS),
    "GET /api/caption-templates": () => json([]),
    "GET /api/brand-templates": () => json([]),
    "GET /api/speech-languages": () => json([{ code: "fr", name: "French" }]),
    "POST /api/subtitles": () => json({ subtitles_id: TOKEN, cues: 3 }, 201),
    "POST /api/sources/probe": () =>
      json({
        url: "https://youtu.be/a",
        title: "Late night set",
        duration: 754,
        thumbnail_url: "",
      }),
  });
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("Home clipping mode and subtitles", () => {
  it("opens the settings panel on Captions only when that chip is pressed", async () => {
    const user = userEvent.setup();
    renderHome();
    await screen.findByText("No projects yet");

    await user.click(screen.getByRole("button", { name: CAPTIONS_CHIP }));
    expect(screen.getByRole("button", { name: CAPTIONS_CHIP })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await user.type(screen.getByLabelText("Video link"), "youtu.be/a");
    await user.click(screen.getByRole("button", { name: "Get clips" }));

    const panel = await screen.findByRole("dialog", { name: "Clip settings" });
    expect(
      await within(panel).findByRole("tab", { name: "Captions only" }),
    ).toHaveAttribute("aria-selected", "true");
  });

  it("warns that a 12 min video in Captions only is one clip, and switches to AI", async () => {
    const user = userEvent.setup();
    renderHome();
    await screen.findByText("No projects yet");

    await user.click(screen.getByRole("button", { name: CAPTIONS_CHIP }));
    await user.type(screen.getByLabelText("Video link"), "youtu.be/a");
    await user.click(screen.getByRole("button", { name: "Get clips" }));

    const panel = await screen.findByRole("dialog", { name: "Clip settings" });
    const note = await within(panel).findByRole("note", {
      name: "Long captions-only clip",
    });
    expect(note).toHaveTextContent("This makes one 12:34 clip, not shorts.");
    await user.click(
      within(note).getByRole("button", { name: "Switch to AI clipping" }),
    );
    expect(
      within(panel).getByRole("tab", { name: "AI clipping" }),
    ).toHaveAttribute("aria-selected", "true");
  });

  it("carries the subtitles attached on Home into the panel's settings", async () => {
    const user = userEvent.setup();
    renderHome();
    await screen.findByText("No projects yet");

    const srt = new File(
      ["1\n00:00:00,000 --> 00:00:01,000\nHi\n"],
      "talk.srt",
    );
    await user.upload(screen.getByLabelText("Upload a subtitles file"), srt);
    expect(await screen.findByText("talk.srt")).toBeVisible();

    await user.type(screen.getByLabelText("Video link"), "youtu.be/a");
    await user.click(screen.getByRole("button", { name: "Get clips" }));

    const panel = await screen.findByRole("dialog", { name: "Clip settings" });
    expect(
      await within(panel).findByRole("button", { name: "Remove subtitles" }),
    ).toBeVisible();
  });
});
