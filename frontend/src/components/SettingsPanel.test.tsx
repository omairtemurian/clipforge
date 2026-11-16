import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProcessingSettings } from "@/api/types";
import { DEFAULTS, json } from "@/testing/mockApi";
import {
  INFO,
  getClips,
  panelRoutes as routes,
  renderPanel,
} from "@/testing/settingsPanel";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SettingsPanel", () => {
  it("submits exactly the ProcessingSettings chosen in the UI", async () => {
    const user = userEvent.setup();
    routes();
    const { onSubmit } = renderPanel();

    expect(await screen.findByText("Late night set")).toBeVisible();
    await user.selectOptions(screen.getByLabelText("Genre"), "faith");
    await user.click(screen.getByRole("button", { name: "60–89s" }));
    await user.click(screen.getByRole("button", { name: "< 30s" }));
    expect(screen.getByRole("button", { name: "Auto (0–3m)" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await user.click(screen.getByRole("button", { name: "More clips" }));
    await user.click(screen.getByRole("button", { name: "More clips" }));
    await user.selectOptions(
      screen.getByLabelText("Speech language"),
      await screen.findByRole("option", { name: "French" }),
    );

    const start = screen.getByRole("slider", { name: "Timeframe start" });
    const end = screen.getByRole("slider", { name: "Timeframe end" });
    expect(start).toHaveAttribute("aria-valuenow", "0");
    expect(end).toHaveAttribute("aria-valuenow", "754");
    start.focus();
    await user.keyboard("{ArrowRight}{ArrowRight}{ArrowRight}");
    expect(screen.getByLabelText("Start time")).toHaveValue("00:03");
    const endTime = screen.getByLabelText("End time");
    await user.clear(endTime);
    await user.type(endTime, "12:30{Enter}");
    expect(end).toHaveAttribute("aria-valuenow", "750");
    expect(screen.getByText("00:03 – 12:30")).toBeVisible();

    await user.click(await screen.findByRole("radio", { name: "Boxed" }));
    await user.selectOptions(screen.getByLabelText("Aspect ratio"), "4:5");
    expect(screen.getByLabelText("Aspect ratio")).toHaveValue("4:5");
    await user.selectOptions(screen.getByLabelText("Aspect ratio"), "1:1");
    await user.selectOptions(
      await screen.findByLabelText("Brand template"),
      await screen.findByRole("option", { name: "Studio" }),
    );
    await user.type(
      screen.getByLabelText("Find moments about…"),
      "  the dentist joke ",
    );
    await user.click(
      screen.getByRole("switch", { name: "Remove filler words" }),
    );
    const autoCut = screen.getByRole("switch", { name: "Auto cut silences" });
    expect(autoCut).toBeChecked();
    expect(
      screen.getByText("Jump cuts over pauses longer than 0.5 s"),
    ).toBeVisible();
    await user.click(autoCut);
    const autoZoom = screen.getByRole("switch", { name: "Auto zoom" });
    expect(autoZoom).toBeChecked();
    await user.click(autoZoom);
    await user.click(screen.getByRole("switch", { name: "Auto headline" }));
    await user.click(
      screen.getByRole("switch", { name: "Auto color correction" }),
    );
    const clipAnything = screen.getByRole("switch", { name: "Clip anything" });
    expect(clipAnything).not.toBeChecked();
    await user.click(clipAnything);
    expect(
      screen.getByRole("switch", { name: "Auto cut silences" }),
    ).toBeDisabled();
    await user.type(screen.getByLabelText("Credit line"), " Ann, CC BY ");
    await getClips(user, "cc_by");

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0][1]).toEqual({
      source_rights: "cc_by",
      credit_line: "Ann, CC BY",
    });
    expect(onSubmit.mock.calls[0][0]).toEqual({
      genre: "faith",
      length_presets: ["lt30", "60_90"],
      custom_length_min_s: null,
      custom_length_max_s: null,
      timeframe_start: 3,
      timeframe_end: 750,
      num_clips: 12,
      aspect: "1:1",
      caption_template: "boxed",
      caption_colors: DEFAULTS.caption_colors,
      keyword_prompt: "the dentist joke",
      remove_fillers: true,
      auto_cut: false,
      auto_cut_min_pause_s: 0.5,
      auto_zoom: false,
      auto_headline: false,
      auto_color: true,
      captions: true,
      language: "fr",
      subtitles_id: null,
      clipping: "ai",
      clip_anything: true,
      search_terms: [],
      brand_template_id: 4,
      reframe_preset: null,
      default_layout: "auto",
      zoom_out_moments: "balanced",
      camera_motion: "calm",
    } satisfies ProcessingSettings);
  });

  it("gives every clip the caption colors chosen over any template", async () => {
    const user = userEvent.setup();
    routes();
    const { onSubmit } = renderPanel();

    await user.click(
      await screen.findByRole("button", { name: "White + green" }),
    );
    expect(screen.getByLabelText("Spoken word color")).toHaveValue("#22c55e");
    await user.click(await screen.findByRole("radio", { name: "Minimal" }));
    expect(screen.getByLabelText("Text color")).toHaveValue("#ffffff");
    expect(screen.getByLabelText("Spoken word color")).toHaveValue("#22c55e");
    fireEvent.input(screen.getByLabelText("Text color"), {
      target: { value: "#00ff00" },
    });
    await getClips(user);

    expect(onSubmit.mock.calls[0][0].caption_template).toBe("minimal");
    expect(onSubmit.mock.calls[0][0].caption_colors).toEqual({
      primary_color: "#00ff00",
      highlight_color: "#22C55E",
      emphasis_color: null,
    });
  });

  it("resets the caption colors to the template's", async () => {
    const user = userEvent.setup();
    routes();
    const { onSubmit } = renderPanel();

    await user.click(
      await screen.findByRole("button", { name: "White + yellow" }),
    );
    await user.click(screen.getByRole("button", { name: "Template colors" }));
    expect(screen.getByLabelText("Spoken word color")).toHaveValue("#ffd23f");
    expect(
      screen.queryByRole("button", { name: "Template colors" }),
    ).toBeNull();
    await getClips(user);

    expect(onSubmit.mock.calls[0][0].caption_colors).toEqual(
      DEFAULTS.caption_colors,
    );
  });

  it("sets the zoom-out moments intensity with a toggle and chips", async () => {
    const user = userEvent.setup();
    routes();
    const { onSubmit } = renderPanel();

    const toggle = await screen.findByRole("switch", {
      name: "Zoom-out moments",
    });
    expect(toggle).toBeChecked();
    expect(screen.getByRole("radio", { name: "Balanced" })).toBeChecked();
    await user.click(screen.getByRole("radio", { name: "Frequent" }));
    await user.click(toggle);
    expect(
      screen.queryByRole("radiogroup", { name: "Zoom-out intensity" }),
    ).toBeNull();
    await user.click(toggle);
    expect(screen.getByRole("radio", { name: "Balanced" })).toBeChecked();
    await user.click(screen.getByRole("radio", { name: "Subtle" }));
    await getClips(user);

    expect(onSubmit.mock.calls[0][0].zoom_out_moments).toBe("subtle");
  });

  it("sets the camera motion, and a reframe style sets its own", async () => {
    const user = userEvent.setup();
    routes();
    const { onSubmit } = renderPanel();

    const motion = await screen.findByRole("radiogroup", {
      name: "Camera motion",
    });
    expect(within(motion).getByRole("radio", { name: "Calm" })).toBeChecked();
    expect(
      screen.getByText(/glides to it in slow, smooth moves/),
    ).toBeVisible();
    await user.click(within(motion).getByRole("radio", { name: "Fast" }));
    const style = screen.getByLabelText("Reframe style");
    await within(style).findByRole("option", { name: "Gaming" });
    await user.selectOptions(style, "gaming");
    expect(within(motion).getByRole("radio", { name: "Calm" })).toBeChecked();
    await user.click(within(motion).getByRole("radio", { name: "Normal" }));
    await getClips(user);

    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      reframe_preset: "gaming",
      camera_motion: "normal",
    });
  });

  it("disables the zoom-out moments for a layout chosen for every clip", async () => {
    const user = userEvent.setup();
    routes();
    renderPanel();

    await user.selectOptions(
      await screen.findByLabelText("Default layout"),
      "split",
    );

    expect(
      screen.getByRole("switch", { name: "Zoom-out moments" }),
    ).toBeDisabled();
  });

  it("makes the timeframe one clip with Captions only", async () => {
    const user = userEvent.setup();
    routes();
    const { onSubmit } = renderPanel();

    await user.click(await screen.findByRole("tab", { name: "Captions only" }));
    expect(screen.queryByLabelText("Genre")).toBeNull();
    expect(
      screen.getByRole("switch", { name: "Auto headline" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("switch", { name: "Clip anything" }),
    ).toBeDisabled();
    await getClips(user);

    expect(onSubmit.mock.calls[0][0]).toEqual({
      ...DEFAULTS,
      clipping: "captions_only",
    });
  });

  it("turns captions off with the No captions tile", async () => {
    const user = userEvent.setup();
    routes();
    const { onSubmit } = renderPanel();

    const noCaptions = await screen.findByRole("radio", {
      name: "No captions",
    });
    await user.click(noCaptions);
    expect(noCaptions).toBeChecked();
    expect(
      screen.getByRole("radio", { name: "Karaoke bold" }),
    ).not.toBeChecked();
    await getClips(user);

    expect(onSubmit.mock.calls[0][0]).toEqual({ ...DEFAULTS, captions: false });
  });

  it("starts from the server's defaults and submits them unchanged", async () => {
    const user = userEvent.setup();
    routes({
      "GET /api/processing-defaults": () => json({ ...DEFAULTS, num_clips: 7 }),
    });
    const { onSubmit } = renderPanel();

    expect(await screen.findByLabelText("Number of clips")).toHaveValue(7);
    const chosen = within(
      screen.getByRole("radiogroup", { name: "Caption template" }),
    );
    expect(
      await chosen.findByRole("radio", { name: "Karaoke bold" }),
    ).toBeChecked();
    expect(screen.getByLabelText("Aspect ratio")).toHaveValue("9:16");
    await getClips(user);

    expect(onSubmit).toHaveBeenCalledWith(
      { ...DEFAULTS, num_clips: 7 },
      { source_rights: "own", credit_line: "" },
    );
  });

  it("needs the source rights before it creates the project", async () => {
    const user = userEvent.setup();
    routes();
    const { onSubmit } = renderPanel();

    const rights = await screen.findByLabelText("Source rights");
    expect(rights).toBeRequired();
    expect(rights).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Get clips" }));
    expect(onSubmit).not.toHaveBeenCalled();

    await getClips(user, "public_domain");

    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("keeps the clip count between 1 and 30", async () => {
    const user = userEvent.setup();
    routes({
      "GET /api/processing-defaults": () =>
        json({ ...DEFAULTS, num_clips: 30 }),
    });
    renderPanel();

    const count = await screen.findByLabelText("Number of clips");
    expect(screen.getByRole("button", { name: "More clips" })).toBeDisabled();
    await user.clear(count);
    await user.type(count, "0");
    await user.tab();

    expect(count).toHaveValue(1);
    expect(screen.getByRole("button", { name: "Fewer clips" })).toBeDisabled();
    await user.clear(count);
    await user.type(count, "12");
    await user.tab();
    expect(count).toHaveValue(12);
  });

  it("shows why a link cannot be read and does not allow Get clips", async () => {
    const user = userEvent.setup();
    let fail = true;
    routes({
      "POST /api/sources/probe": () =>
        fail
          ? json(
              {
                error: "probe_failed",
                message: "it is a playlist, not a video",
              },
              422,
            )
          : json(INFO),
    });
    const { onSubmit } = renderPanel();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "it is a playlist, not a video",
    );
    const getClips = screen.getByRole("button", { name: "Get clips" });
    expect(getClips).toBeDisabled();
    expect(screen.queryByRole("slider")).toBeNull();

    fail = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(getClips).toBeEnabled());
    expect(screen.getAllByRole("slider")).toHaveLength(2);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("has no timeframe slider while the duration is unknown", async () => {
    routes({
      "POST /api/sources/probe": () => json({ ...INFO, duration: null }),
    });
    renderPanel();

    expect(await screen.findByText("Late night set")).toBeVisible();
    expect(await screen.findByLabelText("Genre")).toBeVisible();
    expect(screen.queryByText("Timeframe")).toBeNull();
    expect(screen.queryByLabelText("Start time")).toBeNull();
  });

  it("closes with the X and with Cancel", async () => {
    const user = userEvent.setup();
    routes();
    const { onClose } = renderPanel();

    await user.click(screen.getByRole("button", { name: "Close settings" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("disables Get clips while the project is being created", async () => {
    routes();
    renderPanel(true);

    await screen.findByLabelText("Genre");
    expect(screen.getByRole("button", { name: "Get clips" })).toBeDisabled();
  });
});
