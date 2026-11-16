import { describe, expect, it } from "vitest";
import type { ClipTransitions, TrackItem } from "@/api/types";
import {
  NO_TRANSITIONS,
  TEXT_DEFAULTS,
  pickTransition,
  sectionTransition,
  textProps,
  withAllSections,
  withProps,
  withSectionTransition,
} from "@/lib/overlays";

const ITEM: TrackItem = {
  id: "t1",
  kind: "text",
  asset_id: null,
  start: 0,
  end: 2,
  props: { text: "Hi", size: 0.1 },
};

describe("text layers", () => {
  it("fills in the props a text item does not set", () => {
    expect(textProps(ITEM)).toEqual({
      ...TEXT_DEFAULTS,
      text: "Hi",
      size: 0.1,
    });
  });

  it("changes the props of one item only", () => {
    const other = { ...ITEM, id: "t2" };
    const [changed, kept] = withProps([ITEM, other], "t1", {
      color: "#ff0000",
    });
    expect(changed.props).toEqual({ text: "Hi", size: 0.1, color: "#ff0000" });
    expect(kept).toBe(other);
  });
});

describe("transitions", () => {
  it("picks a kind, keeping the length; none is a hard cut", () => {
    expect(pickTransition("whip", null)).toEqual({
      kind: "whip",
      duration: 0.3,
    });
    expect(pickTransition("slide", { kind: "whip", duration: 0.7 })).toEqual({
      kind: "slide",
      duration: 0.7,
    });
    expect(pickTransition("none", { kind: "whip", duration: 0.7 })).toBeNull();
  });

  it("sets the cut after a section, padding and trimming hard cuts", () => {
    const fade = { kind: "crossfade" as const, duration: 0.3 };
    const set = withSectionTransition(NO_TRANSITIONS, 2, fade);
    expect(set.sections).toEqual([null, null, fade]);
    expect(sectionTransition(set, 2)).toEqual(fade);
    expect(sectionTransition(set, 7)).toBeNull();
    expect(withSectionTransition(set, 2, null).sections).toEqual([]);
  });

  it("copies one transition to every section cut", () => {
    const whip = { kind: "whip" as const, duration: 0.5 };
    const auto: ClipTransitions = { auto: whip, sections: [] };
    expect(withAllSections(auto, 3, whip)).toEqual({
      auto: whip,
      sections: [whip, whip],
    });
    expect(withAllSections(auto, 3, null).sections).toEqual([]);
  });
});
