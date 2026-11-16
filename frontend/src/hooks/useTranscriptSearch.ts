import { useState } from "react";
import type { Word } from "@/api/types";
import { searchWords, type WordRun } from "@/lib/transcriptView";

/** The transcript search as the tool row shows it. */
export interface TranscriptSearchState {
  open: boolean;
  query: string;
  /** How many runs of words match, and which one is active (0-based). */
  count: number;
  active: number;
}

export interface TranscriptSearch {
  state: TranscriptSearchState;
  /** The runs of words that match, in order. */
  matches: WordRun[];
  /** The match the editor points at, null if none. */
  activeMatch: WordRun | null;
  setOpen: (open: boolean) => void;
  setQuery: (query: string) => void;
  step: (direction: 1 | -1) => void;
}

/**
 * The transcript search: whether it is open, its query and the runs of
 * words it matches among those for which visible is true (searchWords),
 * with one active match that Enter / the arrows move through, cycling.
 * Closing it clears the query.
 */
export function useTranscriptSearch(
  words: Word[],
  visible: (index: number) => boolean,
): TranscriptSearch {
  const [open, setOpenState] = useState(false);
  const [query, setQueryState] = useState("");
  const [active, setActive] = useState(0);

  const matches = open
    ? searchWords(words, query).filter(([first]) => visible(first))
    : [];
  const current = matches.length > 0 ? active % matches.length : 0;

  return {
    state: { open, query, count: matches.length, active: current },
    matches,
    activeMatch: matches[current] ?? null,
    setOpen: (next) => {
      setOpenState(next);
      if (!next) setQueryState("");
      setActive(0);
    },
    setQuery: (next) => {
      setQueryState(next);
      setActive(0);
    },
    step: (direction) => {
      if (matches.length === 0) return;
      setActive((current + direction + matches.length) % matches.length);
    },
  };
}
