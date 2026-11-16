import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { Clip, Word } from "@/api/types";
import { AppRoutes } from "@/routes";
import {
  clip,
  json,
  mockRoutes,
  project,
  type Handler,
} from "@/testing/mockApi";

// Clip 10-40 s of a 60 s video: the timeline shows 0-60 s (30 s around the
// clip, inside the video); with the track 600 px wide, 10 px per second.
export const CLIP = clip({ id: 7, start: 10, end: 40, cut_ranges: [[20, 25]] });
const TRACK = { left: 0, top: 0, width: 600, height: 56 };

function word(text: string, start: number, end: number): Word {
  return { text, start, end, speaker: "S0", prob: 0.9, approximate: false };
}

/** The clip's words with context; "skip" lies in the saved cut. */
export const WORDS: Word[] = [
  word("Earlier", 8, 8.5),
  word("words", 8.6, 9.2),
  word("Hello", 10.2, 10.6),
  word("pizza", 10.7, 11.2),
  word("is", 11.3, 11.5),
  word("great", 11.6, 12),
  word("skip", 21, 21.5),
  word("end", 39, 39.5),
  word("Later", 41, 41.5),
  word("on", 41.6, 42),
];

/** Open path in the app with clip data (GET /clips/7), its project and
 * more API routes (which may replace these); returns the fetch mock. */
export function renderAt(
  path: string,
  routes: Record<string, Handler> = {},
  data: Clip = CLIP,
) {
  const fetchMock = mockRoutes({
    "GET /api/clips/7": () => json(data),
    "GET /api/clips/7/transcript": () => json([]),
    "GET /api/projects/1": () => json(project({ id: 1, duration: 60 })),
    ...routes,
  });
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

/** Render the editor of data (GET /clips/7) and its transcript (null: the
 * API answers 409), with more API routes (which may replace these);
 * returns the fetch mock. */
export function renderEditor(
  data: Clip = CLIP,
  words: Word[] | null = WORDS,
  routes: Record<string, Handler> = {},
) {
  return renderAt(
    "/clips/7",
    {
      "GET /api/clips/7/transcript": () =>
        words
          ? json(words)
          : json({ error: "conflict", message: "no transcript.json" }, 409),
      ...routes,
    },
    data,
  );
}

/** The value of one of the clip details (In, Out, Length, Cuts). */
export function stat(label: string) {
  const details = screen.getByRole("region", { name: "Clip details" });
  return within(details).getByText(label).nextElementSibling?.textContent;
}

export function video(): HTMLVideoElement {
  return screen.getByLabelText(/^Preview of/) as HTMLVideoElement;
}

/**
 * jsdom has no layout and does not play media: every element is the 600 px
 * track, and play/pause flip `paused` and fire their events.
 */
export function mockLayoutAndMedia() {
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
    ...TRACK,
    right: TRACK.width,
    bottom: TRACK.height,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
  let paused = true;
  vi.spyOn(HTMLMediaElement.prototype, "paused", "get").mockImplementation(
    () => paused,
  );
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (
    this: HTMLMediaElement,
  ) {
    paused = false;
    fireEvent.play(this);
    return Promise.resolve();
  });
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (
    this: HTMLMediaElement,
  ) {
    paused = true;
    fireEvent.pause(this);
  });
}
