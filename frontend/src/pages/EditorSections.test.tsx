import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Clip, Transcript } from "@/api/types";
import {
  WORDS,
  mockLayoutAndMedia,
  renderEditor,
  video,
} from "@/testing/editor";
import { callsTo, clip, json } from "@/testing/mockApi";

beforeEach(() => {
  mockLayoutAndMedia();
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const TWO: Clip = clip({
  id: 7,
  start: 10,
  end: 40,
  segments: [
    [10, 20],
    [30, 40],
  ],
});

function line(id: number, start: number, text: string) {
  return { id, start, end: start + 3, text, words: [], speaker: "S0" };
}

const SOURCE: Transcript = {
  language: "en",
  duration: 60,
  approximate_times: false,
  segments: [
    line(0, 12, "Inside the first section"),
    line(1, 22, "Pizza in the gap"),
    line(2, 50, "A line at the end"),
  ],
};

async function openSections(routes = {}, data: Clip = TWO) {
  const user = userEvent.setup();
  const fetchMock = renderEditor(data, WORDS, {
    "GET /api/projects/1/transcript": () => json(SOURCE),
    ...routes,
  });
  await screen.findByRole("heading", { name: "Pizza night" });
  await user.click(screen.getByRole("button", { name: "Sections" }));
  return { user, fetchMock };
}

const sectionRows = () =>
  within(screen.getByRole("list", { name: "Sections" })).getAllByRole(
    "listitem",
  );

describe("editor sections panel", () => {
  it("lists the clip's sections in play order", async () => {
    await openSections();

    const rows = sectionRows();
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("00:10.00 – 00:20.00");
    expect(rows[1]).toHaveTextContent("00:30.00 – 00:40.00");
  });

  it("rearranges the sections by dragging one onto another", async () => {
    const answer = clip({
      ...TWO,
      segments: [
        [30, 40],
        [10, 20],
      ],
    });
    const { fetchMock } = await openSections({
      "POST /api/clips/7/sections/reorder": () => json(answer),
    });

    const [first, second] = sectionRows();
    fireEvent.dragStart(first);
    fireEvent.dragOver(second);
    fireEvent.drop(second);

    await waitFor(() =>
      expect(
        callsTo(fetchMock, "POST", "/api/clips/7/sections/reorder"),
      ).toHaveLength(1),
    );
    const [, init] = callsTo(
      fetchMock,
      "POST",
      "/api/clips/7/sections/reorder",
    )[0];
    expect(JSON.parse(String(init?.body))).toEqual({ order: [1, 0] });
    await waitFor(() =>
      expect(sectionRows()[0]).toHaveTextContent("00:30.00 – 00:40.00"),
    );
  });

  it("moves a section with its arrow and deletes one", async () => {
    const { user, fetchMock } = await openSections({
      "POST /api/clips/7/sections/reorder": () => json(TWO),
      "DELETE /api/clips/7/sections/1": () =>
        json(clip({ ...TWO, segments: [[10, 20]] })),
    });

    await user.click(
      screen.getByRole("button", { name: "Move Section 2 earlier" }),
    );
    await waitFor(() =>
      expect(
        callsTo(fetchMock, "POST", "/api/clips/7/sections/reorder"),
      ).toHaveLength(1),
    );
    await user.click(screen.getByRole("button", { name: "Delete Section 2" }));

    await waitFor(() => expect(sectionRows()).toHaveLength(1));
    expect(
      screen.getByRole("button", { name: "Delete Section 1" }),
    ).toBeDisabled();
  });

  it("adds a line of the source transcript as a section", async () => {
    const answer = clip({
      ...TWO,
      segments: [
        [10, 20],
        [30, 40],
        [50, 53],
      ],
    });
    const { user, fetchMock } = await openSections({
      "POST /api/clips/7/sections": () => json(answer),
    });

    await screen.findByText("A line at the end");
    // A line inside a section cannot be added.
    expect(
      screen.getByRole("button", {
        name: "Add section: Inside the first section",
      }),
    ).toBeDisabled();
    await user.type(
      screen.getByLabelText("Search the source transcript"),
      "end",
    );
    expect(screen.queryByText("Pizza in the gap")).toBeNull();
    await user.click(
      screen.getByRole("button", { name: "Add section: A line at the end" }),
    );

    await waitFor(() => expect(sectionRows()).toHaveLength(3));
    const [, init] = callsTo(fetchMock, "POST", "/api/clips/7/sections")[0];
    expect(JSON.parse(String(init?.body))).toEqual({ start: 50, end: 53 });
  });

  it("duplicates the clip and links to the copy", async () => {
    const { user } = await openSections({
      "POST /api/clips/7/duplicate": () =>
        json(clip({ id: 8, title: "Pizza night (copy)" }), 201),
    });

    await user.click(screen.getByRole("button", { name: "Duplicate clip" }));

    const link = await screen.findByRole("link", {
      name: "Pizza night (copy)",
    });
    expect(link).toHaveAttribute("href", "/clips/8");
  });

  it("splits the section and the clip at the playhead", async () => {
    const splitAnswer = clip({
      ...TWO,
      segments: [
        [10, 13],
        [13, 20],
        [30, 40],
      ],
    });
    const { user, fetchMock } = await openSections({
      "POST /api/clips/7/sections/split": () => json(splitAnswer),
      "POST /api/clips/7/split": () =>
        json(
          [
            clip({ ...TWO, segments: [[10, 13]] }),
            clip({ id: 9, title: "Pizza night (part 2)" }),
          ],
          201,
        ),
    });
    const sectionSplit = screen.getByRole("button", {
      name: "Split section in two",
    });
    const clipSplit = screen.getByRole("button", {
      name: "Split into two clips",
    });
    // The preview starts at the clip's start: the edge of a section.
    expect(sectionSplit).toBeDisabled();
    expect(clipSplit).toBeDisabled();

    video().currentTime = 3;
    fireEvent.timeUpdate(video());
    await user.click(sectionSplit);
    await waitFor(() => expect(sectionRows()).toHaveLength(3));
    const [, init] = callsTo(
      fetchMock,
      "POST",
      "/api/clips/7/sections/split",
    )[0];
    expect(JSON.parse(String(init?.body))).toEqual({ at: 13 });

    // The playhead is now on the edge of the two new sections.
    expect(clipSplit).toBeDisabled();
    video().currentTime = 5;
    fireEvent.timeUpdate(video());
    await user.click(clipSplit);
    expect(
      await screen.findByRole("link", { name: "Pizza night (part 2)" }),
    ).toHaveAttribute("href", "/clips/9");
    expect(sectionRows()).toHaveLength(1);
  });
});
