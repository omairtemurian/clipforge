import type { EdlItem } from "@/api/types";

type Params = EdlItem["params"];

/** What the form holds for one param: its text, or a checkbox's state. */
export type ParamDraft = Record<string, string | boolean>;

export interface ParamField {
  key: string;
  type: "number" | "boolean" | "select" | "text";
  options: string[];
  /** The param may be null (an empty field then means null). */
  nullable: boolean;
}

// The values of the enum params of edl_params.py, by param name.
const OPTIONS: Record<string, string[]> = {
  ease: ["linear", "ease_in_out", "back", "elastic"],
  center: ["face", "frame"],
  anchor: ["screen", "face", "object"],
  animation: ["none", "fade", "pop", "slide", "bounce"],
  look: ["bw", "dark", "desat", "lut"],
  fit: ["natural", "stretch"],
  effect: ["bass_boost", "reverb_tail", "lowpass_sweep", "stutter"],
};
const FLASH_COLORS = ["white", "black"];
const TRANSITIONS = ["crossfade", "whip", "zoom", "glitch", "flash", "loop"];
const CAPTION_STYLES = ["pop", "bounce", "single_word", "neon"];

/** The choices of param key of an item of kind, or none (free text). */
function optionsOf(kind: EdlItem["kind"], key: string): string[] {
  if (key === "color" && kind === "flash") return FLASH_COLORS;
  if (key === "type" && kind === "transition") return TRANSITIONS;
  if (key === "style" && kind === "caption_style") return CAPTION_STYLES;
  return OPTIONS[key] ?? [];
}

/** The editable fields of an item's params, one per scalar param, in the
 * order the Director wrote them. */
export function paramFields(item: EdlItem): ParamField[] {
  const fields: ParamField[] = [];
  for (const [key, value] of Object.entries(item.params)) {
    const nullable = value === null;
    if (typeof value === "boolean") {
      fields.push({ key, type: "boolean", options: [], nullable });
    } else if (typeof value === "number") {
      fields.push({ key, type: "number", options: [], nullable });
    } else if (typeof value === "string" || nullable) {
      const options = optionsOf(item.kind, key);
      const type = options.includes(String(value)) ? "select" : "text";
      fields.push({ key, type, options, nullable });
    }
  }
  return fields;
}

/** The form's starting values for item. */
export function draftOf(item: EdlItem): ParamDraft {
  const draft: ParamDraft = {};
  for (const field of paramFields(item)) {
    const value = item.params[field.key];
    draft[field.key] =
      typeof value === "boolean" ? value : value === null ? "" : String(value);
  }
  return draft;
}

export type ParamsResult = { params: Params } | { error: string };

/** The params that draft makes of item's (params the form has no field for
 * stay as they were), or what is wrong with the first bad field. */
export function paramsOf(item: EdlItem, draft: ParamDraft): ParamsResult {
  const params: Params = { ...item.params };
  for (const field of paramFields(item)) {
    const value = draft[field.key];
    if (typeof value === "boolean") {
      params[field.key] = value;
    } else if (value.trim() === "" && field.nullable) {
      params[field.key] = null;
    } else if (field.type === "number") {
      const number = Number(value);
      if (value.trim() === "" || !Number.isFinite(number)) {
        return { error: `${field.key} must be a number` };
      }
      params[field.key] = number;
    } else {
      params[field.key] = value;
    }
  }
  return { params };
}

/** Whether draft differs from the params of item. */
export function draftChanged(item: EdlItem, draft: ParamDraft): boolean {
  const next = paramsOf(item, draft);
  return (
    "error" in next ||
    JSON.stringify(next.params) !== JSON.stringify(item.params)
  );
}
