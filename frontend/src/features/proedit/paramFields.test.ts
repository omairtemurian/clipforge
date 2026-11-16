import { describe, expect, it } from "vitest";
import type { EdlItem } from "@/api/types";
import { edlItem } from "@/testing/proeditFixtures";
import { draftChanged, draftOf, paramFields, paramsOf } from "./paramFields";

const PUNCH: EdlItem = {
  ...edlItem(1, "zoom_punch", 2, 2.5),
  params: { scale: 1.2, ease: "ease_in_out", ease_frames: 0, center: "face" },
};

describe("paramFields", () => {
  it("makes a select of an enum param and a number of a number", () => {
    const fields = paramFields(PUNCH);

    expect(fields.map((f) => [f.key, f.type])).toEqual([
      ["scale", "number"],
      ["ease", "select"],
      ["ease_frames", "number"],
      ["center", "select"],
    ]);
    expect(fields[1].options).toContain("elastic");
  });

  it("tells a flash's color choice from a text pop's hex color", () => {
    const flash = {
      ...edlItem(2, "flash", 1, 1.1),
      params: { color: "white" },
    };
    const text = {
      ...edlItem(3, "text_pop", 1, 2),
      params: { text: "hi", color: "#FFFFFF", animation: "pop" },
    };

    expect(paramFields(flash)[0]).toMatchObject({ type: "select" });
    expect(paramFields(text).map((f) => f.type)).toEqual([
      "text",
      "text",
      "select",
    ]);
  });

  it("has a checkbox per boolean and no field for an item without params", () => {
    const duck = { ...edlItem(4, "music_bed", 0, 5), params: { duck: true } };

    expect(paramFields(duck)[0].type).toBe("boolean");
    expect(paramFields(edlItem(5, "freeze_frame", 1, 2))).toEqual([]);
  });
});

describe("paramsOf", () => {
  it("reads numbers back as numbers and keeps the rest", () => {
    const draft = { ...draftOf(PUNCH), scale: "1.25", ease: "back" };

    expect(paramsOf(PUNCH, draft)).toEqual({
      params: { scale: 1.25, ease: "back", ease_frames: 0, center: "face" },
    });
    expect(draftChanged(PUNCH, draft)).toBe(true);
    expect(draftChanged(PUNCH, draftOf(PUNCH))).toBe(false);
  });

  it("refuses text where a number goes", () => {
    expect(paramsOf(PUNCH, { ...draftOf(PUNCH), scale: "big" })).toEqual({
      error: "scale must be a number",
    });
    expect(paramsOf(PUNCH, { ...draftOf(PUNCH), scale: " " })).toEqual({
      error: "scale must be a number",
    });
  });

  it("turns an empty field of a null param back into null", () => {
    const bed = {
      ...edlItem(6, "music_bed", 0, 5),
      params: { asset: "loop", offset: null },
    };

    expect(draftOf(bed).offset).toBe("");
    expect(paramsOf(bed, { asset: "loop", offset: "" })).toEqual({
      params: { asset: "loop", offset: null },
    });
  });
});
