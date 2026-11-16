import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProcessingPreset, ProcessingSettings } from "@/api/types";
import { DEFAULTS, callsTo, json } from "@/testing/mockApi";
import {
  getClips,
  panelRoutes as routes,
  renderPanel,
} from "@/testing/settingsPanel";

const TOKEN = "ab".repeat(16);

afterEach(() => {
  vi.unstubAllGlobals();
});

/** The JSON body of a recorded fetch call. */
function bodyOf(call: unknown[]): unknown {
  return JSON.parse((call[1] as RequestInit).body as string);
}

describe("SettingsPanel subtitles and presets", () => {
  it("uploads an SRT file and sends its token", async () => {
    const user = userEvent.setup();
    routes({
      "POST /api/subtitles": () => json({ subtitles_id: TOKEN, cues: 12 }, 201),
    });
    const { onSubmit } = renderPanel();

    await user.upload(
      await screen.findByLabelText("Subtitles file"),
      new File(["1\n00:00:01,000 --> 00:00:02,000\nHi\n"], "talk.srt"),
    );
    expect(await screen.findByText("talk.srt")).toBeVisible();
    await getClips(user);
    expect(onSubmit.mock.calls[0][0].subtitles_id).toBe(TOKEN);

    await user.click(screen.getByRole("button", { name: "Remove subtitles" }));
    expect(
      screen.getByRole("button", { name: "Upload SRT or VTT (optional)" }),
    ).toBeVisible();
  });

  it("saves the panel as the default", async () => {
    const user = userEvent.setup();
    const fetchMock = routes({
      "PUT /api/processing-defaults": (_url, init) =>
        json(JSON.parse(init?.body as string) as ProcessingSettings),
    });
    renderPanel();

    await user.selectOptions(await screen.findByLabelText("Genre"), "news");
    await user.click(screen.getByRole("button", { name: "Save as default" }));

    await waitFor(() =>
      expect(
        callsTo(fetchMock, "PUT", "/api/processing-defaults"),
      ).toHaveLength(1),
    );
    const [call] = callsTo(fetchMock, "PUT", "/api/processing-defaults");
    expect(bodyOf(call)).toEqual({ ...DEFAULTS, genre: "news" });
  });

  it("saves, applies and deletes named presets", async () => {
    const user = userEvent.setup();
    let saved: ProcessingPreset[] = [
      { name: "Gaming shorts", settings: { ...DEFAULTS, genre: "gaming" } },
    ];
    const fetchMock = routes({
      "GET /api/processing-presets": () => json(saved),
      "PUT /api/processing-presets": (_url, init) => {
        const preset = JSON.parse(init?.body as string) as ProcessingPreset;
        saved = [...saved, preset];
        return json(preset);
      },
      "DELETE /api/processing-presets/Gaming%20shorts": () => {
        saved = saved.filter((preset) => preset.name !== "Gaming shorts");
        return new Response(null, { status: 204 });
      },
    });
    const { onSubmit } = renderPanel();

    await user.selectOptions(await screen.findByLabelText("Genre"), "vlog");
    await user.click(screen.getByRole("tab", { name: "My presets" }));
    await user.type(screen.getByLabelText("Preset name"), " Travel {Enter}");
    const list = await screen.findByRole("list", { name: "My presets" });
    expect(await within(list).findByText("Travel")).toBeVisible();
    const [put] = callsTo(fetchMock, "PUT", "/api/processing-presets");
    expect(bodyOf(put)).toEqual({
      name: "Travel",
      settings: { ...DEFAULTS, genre: "vlog", keyword_prompt: null },
    });

    await user.click(
      screen.getByRole("button", { name: "Apply Gaming shorts" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Delete Gaming shorts" }),
    );
    await waitFor(() =>
      expect(within(list).queryByText("Gaming shorts")).toBeNull(),
    );
    await getClips(user);

    expect(onSubmit.mock.calls[0][0].genre).toBe("gaming");
  });

  it("ties the copyright notice to the source rights", async () => {
    const user = userEvent.setup();
    routes();
    renderPanel();

    const notice = await screen.findByRole("note", {
      name: "Copyright notice",
    });
    expect(notice).toHaveTextContent("Choose under Source rights");
    await user.selectOptions(
      await screen.findByLabelText("Source rights"),
      "own",
    );

    expect(notice).toHaveTextContent("You confirmed: I own it.");
  });

  it("sends the chosen reframe style, and null for automatic", async () => {
    const user = userEvent.setup();
    routes();
    const { onSubmit } = renderPanel();

    const style = await screen.findByLabelText("Reframe style");
    expect(style).toHaveValue("");
    await screen.findByRole("option", { name: "Gaming" });
    await user.selectOptions(style, "gaming");
    expect(screen.getByText("Fits the whole screen.")).toBeVisible();
    await getClips(user);
    expect(onSubmit.mock.calls[0][0].reframe_preset).toBe("gaming");
  });

  it("sends the chosen default layout", async () => {
    const user = userEvent.setup();
    routes();
    const { onSubmit } = renderPanel();

    const layout = await screen.findByLabelText("Default layout");
    expect(layout).toHaveValue("auto");
    await user.selectOptions(layout, "dynamic");
    expect(screen.getByText(/switch layout at scene cuts/)).toBeVisible();
    await user.selectOptions(layout, "screenshare");
    await getClips(user);
    expect(onSubmit.mock.calls[0][0].default_layout).toBe("screenshare");
  });
});
