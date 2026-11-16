import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CleanupSuggestion } from "@/api/types";
import { mockLayoutAndMedia, renderEditor, stat } from "@/testing/editor";
import { json } from "@/testing/mockApi";

beforeEach(mockLayoutAndMedia);

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const SUGGESTIONS: CleanupSuggestion[] = [
  { start: 11.25, end: 11.55, kind: "filler", text: "is" },
  { start: 12.15, end: 19.9, kind: "pause", text: "" },
  { start: 21, end: 21.5, kind: "filler", text: "skip" },
];

function renderWithSuggestions() {
  return renderEditor(undefined, undefined, {
    "GET /api/clips/7/cleanup-suggestions?start=10&end=40": () =>
      json(SUGGESTIONS),
  });
}

async function clipWord(text: string) {
  const words = await screen.findByLabelText("Clip words");
  return within(words).getByText(text);
}

async function drag(first: string, last: string) {
  fireEvent.pointerDown(await clipWord(first), { button: 0, pointerId: 1 });
  fireEvent.pointerEnter(await clipWord(last));
  fireEvent.pointerUp(window);
}

describe("speech cleanup", () => {
  it("cuts only the checked suggestions, in one undo step", async () => {
    const user = userEvent.setup();
    renderWithSuggestions();
    await clipWord("Hello");
    await user.click(screen.getByRole("button", { name: "Speech cleanup" }));

    const dialog = await screen.findByRole("dialog", {
      name: "Speech cleanup",
    });
    const boxes = await within(dialog).findAllByRole("checkbox");
    expect(boxes).toHaveLength(3);
    expect(boxes[2]).toBeDisabled();
    expect(within(dialog).getByText("Already removed")).toBeVisible();

    await user.click(boxes[1]);
    expect(boxes[1]).not.toBeChecked();
    await user.click(
      within(dialog).getByRole("button", { name: "Remove 1 cut" }),
    );

    expect(screen.queryByRole("dialog")).toBe(null);
    expect(await clipWord("is")).toHaveAttribute("data-cut", "true");
    expect(screen.getByLabelText("Pause 9s")).not.toHaveAttribute("data-cut");
    expect(stat("Cuts")).toBe("2");

    await user.click(screen.getByRole("button", { name: "Speech cleanup" }));
    const again = await screen.findByRole("dialog");
    // "is" is cut now; the pause is offered again, checked.
    await user.click(
      await within(again).findByRole("button", { name: "Remove 1 cut" }),
    );
    expect(screen.getByLabelText("Pause 9s (cut)")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(stat("Cuts")).toBe("2");
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(stat("Cuts")).toBe("1");
  });

  it("says so when there is nothing to clean up", async () => {
    const user = userEvent.setup();
    renderEditor(undefined, undefined, {
      "GET /api/clips/7/cleanup-suggestions?start=10&end=40": () => json([]),
    });
    await clipWord("Hello");
    await user.click(screen.getByRole("button", { name: "Speech cleanup" }));
    expect(
      await screen.findByText(
        "No filler words or long pauses were found in this clip.",
      ),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Remove 0 cuts" }),
    ).toBeDisabled();
  });
});

describe("selection toolbar", () => {
  it("deletes the selected words", async () => {
    const user = userEvent.setup();
    renderEditor();
    await drag("pizza", "great");

    const toolbar = screen.getByRole("toolbar", { name: "Selected words" });
    await user.click(within(toolbar).getByRole("button", { name: "Delete" }));

    expect(await clipWord("is")).toHaveAttribute("data-cut", "true");
    expect(stat("Cuts")).toBe("2");
    expect(screen.queryByRole("toolbar", { name: "Selected words" })).toBe(
      null,
    );
  });

  it("uses the selected words as the hook or the title", async () => {
    const user = userEvent.setup();
    renderEditor();
    await drag("Hello", "pizza");

    await user.click(screen.getByRole("button", { name: "Add caption" }));
    await user.click(
      await screen.findByRole("menuitem", { name: "Use as hook" }),
    );
    const details = screen.getByRole("region", { name: "Clip details" });
    expect(details).toHaveTextContent("Hook Hello pizza");

    await drag("is", "great");
    await user.click(screen.getByRole("button", { name: "Add caption" }));
    await user.click(
      await screen.findByRole("menuitem", { name: "Use as title" }),
    );
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "is great",
    );
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Pizza night",
    );
  });
});

describe("transcript search and playback", () => {
  it("marks the words a search finds and steps through them", async () => {
    const user = userEvent.setup();
    renderEditor();
    await clipWord("Hello");
    await user.click(
      screen.getByRole("button", { name: "Search the transcript" }),
    );
    await user.type(screen.getByRole("searchbox"), "e");

    // Hello, great and end; context words are hidden, so not searched.
    expect(screen.getByLabelText("Matches")).toHaveTextContent("1/3");
    expect(await clipWord("great")).toHaveAttribute("data-match", "true");
    expect(await clipWord("pizza")).not.toHaveAttribute("data-match");
    await user.keyboard("{Enter}");
    expect(screen.getByLabelText("Matches")).toHaveTextContent("2/3");
    await user.keyboard("{Shift>}{Enter}{/Shift}{Shift>}{Enter}{/Shift}");
    expect(screen.getByLabelText("Matches")).toHaveTextContent("3/3");

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("searchbox")).toBe(null);
    expect(await clipWord("great")).not.toHaveAttribute("data-match");
  });

  it("marks the word being played", async () => {
    const user = userEvent.setup();
    renderEditor();
    fireEvent.pointerDown(await clipWord("pizza"), { button: 0, pointerId: 1 });
    fireEvent.pointerUp(window);
    expect(await clipWord("pizza")).not.toHaveAttribute("data-current");

    await user.keyboard(" ");
    await waitFor(async () =>
      expect(await clipWord("pizza")).toHaveAttribute("data-current", "true"),
    );
  });
});
