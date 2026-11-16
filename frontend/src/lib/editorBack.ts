/** The navigation state of a page that opens the clip editor and wants the
 * editor's back arrow to return to it. */
export interface EditorBackState {
  backTo: string;
  backLabel: string;
}

/** Where the editor's back arrow goes: the page that opened it (its
 * EditorBackState in the navigation state), else the project's clips. */
export function backLink(
  state: unknown,
  projectId: number,
): { to: string; label: string } {
  const from = (state ?? {}) as Partial<Record<keyof EditorBackState, unknown>>;
  if (typeof from.backTo === "string" && typeof from.backLabel === "string") {
    return { to: from.backTo, label: from.backLabel };
  }
  return { to: `/projects/${projectId}`, label: "Back to clips" };
}
