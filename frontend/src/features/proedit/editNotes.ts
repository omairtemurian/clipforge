/** One line of a run's notes about an item the Director's post-processing
 * moved or dropped, or a composite move it left out
 * ("Dropped shake at 16.37 s: over the standard budget …"). */
export interface EditNote {
  action: "Moved" | "Dropped" | "Left out";
  kind: string;
  seconds: number;
  reason: string;
}

const EDIT_NOTE = /^(Moved|Dropped|Left out) (\S+) at ([\d.]+) s: (.*)$/s;

/** The edit note of a note line, or null for any other note (the critic's,
 * a fallback reason). */
export function parseEditNote(note: string): EditNote | null {
  const match = EDIT_NOTE.exec(note);
  if (!match) return null;
  return {
    action: match[1] as EditNote["action"],
    kind: match[2],
    seconds: Number(match[3]),
    reason: match[4],
  };
}

/** Split a run's notes into its edit notes and the others. */
export function splitNotes(notes: string[]): {
  edits: EditNote[];
  others: string[];
} {
  const edits: EditNote[] = [];
  const others: string[] = [];
  for (const note of notes) {
    const edit = parseEditNote(note);
    if (edit) edits.push(edit);
    else others.push(note);
  }
  return { edits, others };
}
