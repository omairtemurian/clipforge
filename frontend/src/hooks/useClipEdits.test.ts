import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { NO_STYLE } from "@/lib/clipLook";
import { DEFAULT_FRAMING } from "@/lib/cropFrame";
import { clip } from "@/testing/mockApi";
import { useClipEdits } from "./useClipEdits";

const CLIP = clip({ id: 7, start: 10, end: 40, cut_ranges: [[20, 25]] });

describe("useClipEdits look", () => {
  it("starts with the saved look and a PATCH body that repeats it", () => {
    const { result } = renderHook(() => useClipEdits(CLIP));

    expect(result.current.look).toEqual({
      layout: "fill",
      caption_template: "karaoke_bold",
      caption_style: NO_STYLE,
      caption_overrides: [],
      crop_offset: 0,
      framing: DEFAULT_FRAMING,
      auto_cut: false,
      auto_zoom: false,
      zoom_keyframes: [],
    });
    expect(result.current.patch).toEqual({
      start: 10,
      end: 40,
      cut_ranges: [[20, 25]],
      title: "Pizza night",
      hook_text: "He ate it all",
      description: "A man and a whole pizza.",
      hashtags: ["pizza", "funny", "standup"],
      layout: "fill",
      caption_template: "karaoke_bold",
      caption_style: NO_STYLE,
      caption_overrides: [],
      crop_offset: 0,
      framing: DEFAULT_FRAMING,
      auto_cut: false,
      auto_zoom: false,
      zoom_keyframes: [],
      scene_reframes: [],
      transitions: { auto: null, sections: [] },
    });
    expect(result.current.canUndo).toBe(false);
  });

  it("puts the look edits in the PATCH body", () => {
    const { result } = renderHook(() => useClipEdits(CLIP));
    const override = {
      text: "Hallo",
      start: 10.2,
      end: 10.6,
      speaker: "S0",
      prob: 0.9,
      approximate: false,
    };

    act(() =>
      result.current.setLook({
        layout: "split",
        caption_template: "neon",
        caption_style: { ...NO_STYLE, size: 96, uppercase: false },
        caption_overrides: [override],
        crop_offset: -0.25,
      }),
    );

    expect(result.current.patch).toMatchObject({
      layout: "split",
      caption_template: "neon",
      caption_style: { ...NO_STYLE, size: 96, uppercase: false },
      caption_overrides: [override],
      crop_offset: -0.25,
      start: 10,
      end: 40,
    });
  });

  it("undoes look edits one step at a time, a gesture at once", () => {
    const { result } = renderHook(() => useClipEdits(CLIP));

    act(() => result.current.setLook({ layout: "fit" }));
    act(() => result.current.setLook({ crop_offset: 0.1 }, 5));
    act(() => result.current.setLook({ crop_offset: 0.2 }, 5));
    act(() => result.current.setLook({ crop_offset: 0.3 }, 5));
    expect(result.current.look.crop_offset).toBe(0.3);

    act(() => result.current.undo());
    expect(result.current.look).toMatchObject({
      layout: "fit",
      crop_offset: 0,
    });
    act(() => result.current.undo());
    expect(result.current.look.layout).toBe("fill");
    act(() => result.current.redo());
    expect(result.current.look.layout).toBe("fit");
  });
});

describe("useClipEdits dirty", () => {
  it("is dirty from the first edit until it is undone or saved", () => {
    const { result, rerender } = renderHook(
      ({ saved }) => useClipEdits(saved),
      { initialProps: { saved: CLIP } },
    );
    expect(result.current.dirty).toBe(false);

    act(() => result.current.setTexts({ hashtags: ["a", "b", "c"] }));
    expect(result.current.dirty).toBe(true);
    expect(result.current.patch.hashtags).toEqual(["a", "b", "c"]);

    act(() => result.current.undo());
    expect(result.current.dirty).toBe(false);

    act(() => result.current.setTexts({ description: "New" }));
    expect(result.current.dirty).toBe(true);
    rerender({ saved: { ...CLIP, description: "New" } });
    expect(result.current.dirty).toBe(false);
  });

  it("is not dirty for a split, which is not saved", () => {
    const { result } = renderHook(() => useClipEdits(CLIP));

    act(() => result.current.split(15));

    expect(result.current.splits).toEqual([15]);
    expect(result.current.dirty).toBe(false);
  });

  it("is not dirty once its layers are saved with their defaults filled in", () => {
    const { result, rerender } = renderHook(
      ({ saved }) => useClipEdits(saved),
      { initialProps: { saved: CLIP } },
    );
    const text = {
      id: "text-1",
      kind: "text" as const,
      asset_id: null,
      start: 0,
      end: 3,
      props: { text: "Big news", animation_in: "pop", box: "#000000" },
    };

    act(() => result.current.setLayer("text", [text]));
    expect(result.current.layersDirty).toBe(true);

    // PATCH /clips/{id}/tracks answers with the props' defaults filled in.
    const props = {
      text: "Big news",
      font: "Montserrat ExtraBold",
      size: 0.06,
      color: "#FFFFFF",
      stroke: null,
      stroke_width: 0.08,
      box: "#000000",
      box_opacity: 1,
      x: 0.5,
      y: 0.2,
      animation_in: "pop",
      animation_out: "none",
      in_seconds: 0.4,
      out_seconds: 0.4,
    };
    rerender({
      saved: {
        ...CLIP,
        tracks: { ...CLIP.tracks, text: [{ ...text, props }] },
      },
    });
    expect(result.current.layersDirty).toBe(false);
    expect(result.current.dirty).toBe(false);

    act(() =>
      result.current.setLayer("text", [
        { ...text, props: { ...text.props, box: null } },
      ]),
    );
    expect(result.current.dirty).toBe(true);
  });
});
