import type { Project } from "@/api/types";

export type SourceRights = NonNullable<Project["source_rights"]>;

/** Why the owner may use a source video, as the project stores it. */
export interface RightsChoice {
  source_rights: SourceRights;
  credit_line: string;
}

export const RIGHTS_OPTIONS: { value: SourceRights; label: string }[] = [
  { value: "own", label: "I own it" },
  { value: "permission", label: "I have the creator's permission" },
  { value: "cc_by", label: "Creative Commons (CC BY)" },
  { value: "public_domain", label: "Public domain" },
  { value: "other", label: "Other / fair use" },
];

export const CREDIT_LINE_MAX = 200;
