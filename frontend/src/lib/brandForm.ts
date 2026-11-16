/**
 * The brand template form: its draft, the checks that mirror the API's
 * (models.BrandTemplate, clipforge.brand_files) and the multipart body.
 */
import type { BrandTemplate } from "@/api/types";

export const LOGO_MAX_BYTES = 5 * 1024 * 1024;
export const LOGO_TYPES = ["image/png", "image/jpeg", "image/webp"];
export const VIDEO_SUFFIXES = [".mp4", ".mov", ".m4v", ".webm", ".mkv"];
export const DEFAULT_FONT = "Inter Bold";
export const DEFAULT_COLOR = "#ff6b35";

export type LogoPosition = BrandTemplate["logo_position"];
export type VideoKind = "intro" | "outro";

export interface BrandDraft {
  name: string;
  position: LogoPosition;
  opacity: number;
  font: string;
  color: string;
  /** A newly picked logo; null keeps the saved one. */
  logo: File | null;
  intro: File | null;
  outro: File | null;
  /** Drop the saved intro / outro (ignored when a new video is picked). */
  removeIntro: boolean;
  removeOutro: boolean;
}

export type BrandProblems = Partial<
  Record<"name" | "logo" | "intro" | "outro" | "font", string>
>;

/** A draft with the values of a new template, or those of `template`. */
export function draftOf(template?: BrandTemplate): BrandDraft {
  return {
    name: template?.name ?? "",
    position: template?.logo_position ?? "br",
    opacity: template?.logo_opacity ?? 0.8,
    font: template?.font ?? DEFAULT_FONT,
    color: (template?.primary_color ?? DEFAULT_COLOR).toLowerCase(),
    logo: null,
    intro: null,
    outro: null,
    removeIntro: false,
    removeOutro: false,
  };
}

/** The last part of a stored file path: "/data/brand/3/intro.mp4" -> "intro.mp4". */
export function fileName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

function logoProblem(logo: File): string | undefined {
  if (!LOGO_TYPES.includes(logo.type)) return "Use a PNG, JPEG or WebP image.";
  if (logo.size === 0) return "The file is empty.";
  if (logo.size > LOGO_MAX_BYTES) return "The logo must be 5 MB or smaller.";
  return undefined;
}

function videoProblem(video: File): string | undefined {
  const name = video.name.toLowerCase();
  if (!VIDEO_SUFFIXES.some((suffix) => name.endsWith(suffix)))
    return `Use a video file (${VIDEO_SUFFIXES.join(", ")}).`;
  if (video.size === 0) return "The file is empty.";
  return undefined;
}

/**
 * What is wrong with draft, by field (a field that is fine is absent).
 * `hasLogo` tells that the template being edited already has a logo, which a
 * new template needs picked; `fonts` are the names the API accepts.
 */
export function validateBrand(
  draft: BrandDraft,
  hasLogo: boolean,
  fonts: string[],
): BrandProblems {
  const problems: BrandProblems = {};
  if (draft.name.trim() === "") problems.name = "Give the template a name.";
  if (draft.logo) {
    const problem = logoProblem(draft.logo);
    if (problem) problems.logo = problem;
  } else if (!hasLogo) {
    problems.logo = "Choose a logo image.";
  }
  if (draft.intro) {
    const problem = videoProblem(draft.intro);
    if (problem) problems.intro = problem;
  }
  if (draft.outro) {
    const problem = videoProblem(draft.outro);
    if (problem) problems.outro = problem;
  }
  if (fonts.length > 0 && !fonts.includes(draft.font))
    problems.font = "Pick one of the listed fonts.";
  return problems;
}

/**
 * The multipart body of POST (new) or PUT /brand-templates: the fields, the
 * picked files and, for a saved template, the intro / outro to drop.
 */
export function brandFormData(draft: BrandDraft): FormData {
  const form = new FormData();
  form.set("name", draft.name.trim());
  form.set("logo_position", draft.position);
  form.set("logo_opacity", String(draft.opacity));
  form.set("font", draft.font);
  form.set("primary_color", draft.color);
  if (draft.logo) form.set("logo", draft.logo);
  if (draft.intro) form.set("intro", draft.intro);
  if (draft.outro) form.set("outro", draft.outro);
  if (draft.removeIntro) form.set("remove_intro", "true");
  if (draft.removeOutro) form.set("remove_outro", "true");
  return form;
}
