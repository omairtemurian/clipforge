import { describe, expect, it } from "vitest";
import type { BrandTemplate } from "@/api/types";
import {
  brandFormData,
  draftOf,
  fileName,
  LOGO_MAX_BYTES,
  validateBrand,
} from "./brandForm";

const FONTS = ["Inter", "Inter Bold"];

const SAVED: BrandTemplate = {
  id: 3,
  name: "Acme",
  logo_path: "/data/brand/3/logo.png",
  logo_position: "tl",
  logo_opacity: 0.5,
  font: "Inter",
  primary_color: "#00AAFF",
  intro_path: "/data/brand/3/intro.mp4",
  outro_path: null,
};

function file(name: string, type: string, size = 10): File {
  return new File([new Uint8Array(size)], name, { type });
}

describe("draftOf", () => {
  it("starts a new template with the API defaults", () => {
    expect(draftOf()).toMatchObject({
      name: "",
      position: "br",
      opacity: 0.8,
      font: "Inter Bold",
      color: "#ff6b35",
      logo: null,
    });
  });

  it("copies a saved template, with a lower-case color", () => {
    expect(draftOf(SAVED)).toMatchObject({
      name: "Acme",
      position: "tl",
      opacity: 0.5,
      font: "Inter",
      color: "#00aaff",
    });
  });
});

describe("validateBrand", () => {
  it("asks for a name and, for a new template, a logo", () => {
    expect(validateBrand(draftOf(), false, FONTS)).toEqual({
      name: "Give the template a name.",
      logo: "Choose a logo image.",
    });
  });

  it("accepts a blank-free name with a PNG logo", () => {
    const draft = {
      ...draftOf(),
      name: "Acme",
      logo: file("a.png", "image/png"),
    };
    expect(validateBrand(draft, false, FONTS)).toEqual({});
  });

  it("treats a name of blanks as empty", () => {
    const draft = { ...draftOf(SAVED), name: "   " };
    expect(validateBrand(draft, true, FONTS).name).toBeDefined();
  });

  it("keeps the saved logo when none is picked", () => {
    expect(validateBrand(draftOf(SAVED), true, FONTS)).toEqual({});
  });

  it("rejects a logo that is not an image, empty or over 5 MB", () => {
    const base = draftOf(SAVED);
    const check = (logo: File) => validateBrand({ ...base, logo }, true, FONTS);
    expect(check(file("a.gif", "image/gif")).logo).toMatch(/PNG, JPEG or WebP/);
    expect(check(file("a.png", "image/png", 0)).logo).toMatch(/empty/);
    expect(check(file("a.png", "image/png", LOGO_MAX_BYTES + 1)).logo).toMatch(
      /5 MB/,
    );
    expect(check(file("a.webp", "image/webp", LOGO_MAX_BYTES)).logo).toBe(
      undefined,
    );
  });

  it("rejects an intro or outro without a video suffix", () => {
    const draft = {
      ...draftOf(SAVED),
      intro: file("intro.png", "image/png"),
      outro: file("OUTRO.MOV", "video/quicktime"),
    };
    const problems = validateBrand(draft, true, FONTS);
    expect(problems.intro).toMatch(/video file/);
    expect(problems.outro).toBeUndefined();
  });

  it("rejects a font that is not listed, once the list is known", () => {
    const draft = { ...draftOf(SAVED), font: "Comic Sans" };
    expect(validateBrand(draft, true, FONTS).font).toBeDefined();
    expect(validateBrand(draft, true, []).font).toBeUndefined();
  });
});

describe("brandFormData", () => {
  it("sends the fields, trimmed, and only the picked files", () => {
    const logo = file("a.png", "image/png");
    const form = brandFormData({
      ...draftOf(SAVED),
      name: " Acme ",
      logo,
      removeIntro: true,
    });
    expect(form.get("name")).toBe("Acme");
    expect(form.get("logo_position")).toBe("tl");
    expect(form.get("logo_opacity")).toBe("0.5");
    expect(form.get("font")).toBe("Inter");
    expect(form.get("primary_color")).toBe("#00aaff");
    expect((form.get("logo") as File).name).toBe("a.png");
    expect(form.has("intro")).toBe(false);
    expect(form.get("remove_intro")).toBe("true");
    expect(form.has("remove_outro")).toBe(false);
  });
});

describe("fileName", () => {
  it("returns the last path part", () => {
    expect(fileName("/data/brand/3/intro.mp4")).toBe("intro.mp4");
    expect(fileName("C:\\brand\\logo.png")).toBe("logo.png");
  });
});
