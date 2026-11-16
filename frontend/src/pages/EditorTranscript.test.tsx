import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  mockLayoutAndMedia,
  renderEditor,
  stat,
  video,
} from "@/testing/editor";

beforeEach(mockLayoutAndMedia);

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function clipWord(text: string) {
  const words = await screen.findByLabelText("Clip words");
  return within(words).getByText(text);
}

function press(element: Element, init: PointerEventInit = {}) {
  fireEvent.pointerDown(element, { button: 0, pointerId: 1, ...init });
}

/** Select the clip words from first to last by dragging across them. */
async function drag(first: string, last: string) {
  press(await clipWord(first));
  fireEvent.pointerEnter(await clipWord(last));
  fireEvent.pointerUp(window);
}

const cutTitle = (from: string, to: string) => `Cut ${from} - ${to}`;

describe("transcript editor", () => {
  it("shows the clip's words, and grayed context to extend it", async () => {
    const user = userEvent.setup();
    renderEditor();
    await clipWord("Hello");
    expect(screen.queryByRole("region", { name: "Before the clip" })).toBe(
      null,
    );

    await user.click(screen.getByRole("button", { name: "Extend a clip" }));
    const before = await screen.findByRole("region", {
      name: "Before the clip",
    });
    expect(before).toHaveTextContent("Earlier words");
    expect(
      screen.getByRole("region", { name: "After the clip" }),
    ).toHaveTextContent("Later on");
    // Pauses of 0.3 s or more show as pills with their length.
    expect(screen.getByLabelText("Clip words")).toHaveTextContent(
      "Hello pizza is great 9s skip 17.5s end",
    );
    expect(screen.getByLabelText("Pause 9s")).toBeVisible();
    expect(await clipWord("skip")).toHaveAttribute("data-cut", "true");
    expect(await clipWord("pizza")).not.toHaveAttribute("data-cut");
  });

  it("plays from a clicked word", async () => {
    renderEditor();
    press(await clipWord("pizza"));
    expect(video().currentTime).toBeCloseTo(0.7);
    expect(await clipWord("pizza")).toHaveAttribute("data-selected", "true");

    // 39 s of source is 24 s into the preview (the 5 s cut skipped).
    press(await clipWord("end"));
    expect(video().currentTime).toBeCloseTo(24);
  });

  it("cuts the selected words with Delete, and undoes and redoes it", async () => {
    const user = userEvent.setup();
    renderEditor();
    await drag("pizza", "great");
    expect(await clipWord("is")).toHaveAttribute("data-selected", "true");

    await user.keyboard("{Delete}");

    for (const text of ["pizza", "is", "great"]) {
      expect(await clipWord(text)).toHaveAttribute("data-cut", "true");
    }
    expect(await clipWord("Hello")).not.toHaveAttribute("data-cut");
    expect(stat("Cuts")).toBe("2");
    expect(stat("Length")).toBe("00:23.70");
    expect(screen.getByTitle(cutTitle("00:10.70", "00:12.00"))).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(await clipWord("pizza")).not.toHaveAttribute("data-cut");
    expect(stat("Cuts")).toBe("1");

    await user.click(screen.getByRole("button", { name: "Redo" }));
    expect(stat("Cuts")).toBe("2");
    (document.activeElement as HTMLElement).blur();
    await user.keyboard("{Meta>}z{/Meta}");
    expect(stat("Cuts")).toBe("1");
    await user.keyboard("{Meta>}{Shift>}z{/Shift}{/Meta}");
    expect(stat("Cuts")).toBe("2");
  });

  it("extends a selection with shift+click and clears it with Escape", async () => {
    const user = userEvent.setup();
    renderEditor();
    press(await clipWord("Hello"));
    press(await clipWord("is"), { shiftKey: true });
    expect(await clipWord("pizza")).toHaveAttribute("data-selected", "true");

    await user.keyboard("{Escape}");
    expect(await clipWord("pizza")).not.toHaveAttribute("data-selected");
    await user.keyboard("{Delete}");
    expect(stat("Cuts")).toBe("1");
  });

  it("restores a cut word when it is clicked", async () => {
    const user = userEvent.setup();
    renderEditor();
    await user.click(await clipWord("skip"));

    expect(await clipWord("skip")).not.toHaveAttribute("data-cut");
    expect(stat("Cuts")).toBe("0");
    expect(stat("Length")).toBe("00:30.00");
    expect(screen.getByRole("button", { name: "Undo" })).toBeEnabled();
  });

  it("extends the clip to a context word", async () => {
    const user = userEvent.setup();
    renderEditor();
    await user.click(
      await screen.findByRole("button", { name: "Extend a clip" }),
    );
    const before = await screen.findByRole("region", {
      name: "Before the clip",
    });
    await user.click(within(before).getByText("words"));
    await user.click(screen.getByRole("button", { name: "Extend to here" }));
    expect(stat("In")).toBe("00:08.60");
    expect(screen.getByLabelText("Clip words")).toHaveTextContent(
      /^words 1s Hello/,
    );

    const after = screen.getByRole("region", { name: "After the clip" });
    await user.click(within(after).getByText("on"));
    await user.click(screen.getByRole("button", { name: "Extend to here" }));
    expect(stat("Out")).toBe("00:42.00");
    expect(screen.queryByRole("region", { name: "After the clip" })).toBe(null);
  });

  it("undoes a whole handle drag in one step", async () => {
    const user = userEvent.setup();
    renderEditor();
    const end = await screen.findByRole("slider", { name: "Clip end" });
    expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();

    fireEvent.pointerDown(end, { button: 0, clientX: 450, pointerId: 1 });
    fireEvent.pointerMove(end, { clientX: 350, pointerId: 1 });
    fireEvent.pointerMove(end, { clientX: 300, pointerId: 1 });
    fireEvent.pointerUp(end, { pointerId: 1 });
    expect(stat("Out")).toBe("00:30.00");

    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(stat("Out")).toBe("00:40.00");
    expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
  });

  it("plays and pauses with Space", async () => {
    const user = userEvent.setup();
    renderEditor();
    await clipWord("Hello");

    await user.keyboard(" ");
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
    await user.keyboard(" ");
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
  });

  it("says so when the transcript cannot be loaded", async () => {
    renderEditor(undefined, null);
    expect(
      await screen.findByText("The transcript could not be loaded."),
    ).toBeVisible();
    expect(screen.getByLabelText("Clip length")).toHaveTextContent("00:25.00");
  });

  it("says so when no words are spoken in the clip", async () => {
    renderEditor(undefined, []);
    expect(
      await screen.findByText("No words are spoken in this clip."),
    ).toBeVisible();
  });
});
