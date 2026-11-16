import { describe, expect, it, vi } from "vitest";
import { handleEditorKey } from "./useEditorShortcuts";

function handlers(deleted = true, clipboard = true) {
  return {
    copy: vi.fn(() => clipboard),
    paste: vi.fn(() => clipboard),
    speed: vi.fn(),
    togglePlay: vi.fn(),
    deleteSelection: vi.fn(() => deleted),
    clearSelection: vi.fn(),
    undo: vi.fn(),
    redo: vi.fn(),
    split: vi.fn(),
    zoom: vi.fn(),
    step: vi.fn(),
  };
}

function press(
  init: KeyboardEventInit,
  target: Element = document.body,
  deleted = true,
  clipboard = true,
) {
  const event = new KeyboardEvent("keydown", { cancelable: true, ...init });
  Object.defineProperty(event, "target", { value: target });
  const spy = handlers(deleted, clipboard);
  handleEditorKey(event, spy);
  return { event, spy };
}

describe("editor shortcuts", () => {
  it("copies and pastes the timeline item with cmd/ctrl+C and +V", () => {
    const copy = press({ key: "c", metaKey: true });
    expect(copy.spy.copy).toHaveBeenCalled();
    expect(copy.event.defaultPrevented).toBe(true);
    const paste = press({ key: "v", ctrlKey: true });
    expect(paste.spy.paste).toHaveBeenCalled();
    expect(paste.event.defaultPrevented).toBe(true);
  });

  it("leaves cmd+C and cmd+V to the browser with nothing to copy", () => {
    const copy = press({ key: "c", metaKey: true }, document.body, true, false);
    expect(copy.spy.copy).toHaveBeenCalled();
    expect(copy.event.defaultPrevented).toBe(false);
    const input = document.createElement("input");
    const typed = press({ key: "v", metaKey: true }, input);
    expect(typed.spy.paste).not.toHaveBeenCalled();
  });

  it("changes the playback speed with < and >", () => {
    expect(press({ key: ">", shiftKey: true }).spy.speed).toHaveBeenCalledWith(
      1,
    );
    const slower = press({ key: "<", shiftKey: true });
    expect(slower.spy.speed).toHaveBeenCalledWith(-1);
    expect(slower.event.defaultPrevented).toBe(true);
    expect(press({ key: ">", metaKey: true }).spy.speed).not.toHaveBeenCalled();
  });

  it("undoes with cmd/ctrl+Z and redoes with shift or ctrl+Y", () => {
    expect(press({ key: "z", metaKey: true }).spy.undo).toHaveBeenCalled();
    expect(press({ key: "z", ctrlKey: true }).spy.undo).toHaveBeenCalled();
    const redo = press({ key: "Z", metaKey: true, shiftKey: true });
    expect(redo.spy.redo).toHaveBeenCalled();
    expect(redo.spy.undo).not.toHaveBeenCalled();
    expect(redo.event.defaultPrevented).toBe(true);
    expect(press({ key: "y", ctrlKey: true }).spy.redo).toHaveBeenCalled();
  });

  it("cuts the selection with Delete or Backspace", () => {
    const del = press({ key: "Delete" });
    expect(del.spy.deleteSelection).toHaveBeenCalled();
    expect(del.event.defaultPrevented).toBe(true);
    expect(press({ key: "Backspace" }).spy.deleteSelection).toHaveBeenCalled();
    const none = press({ key: "Delete" }, document.body, false);
    expect(none.event.defaultPrevented).toBe(false);
  });

  it("plays or pauses with Space, except on a button or slider", () => {
    const space = press({ key: " " });
    expect(space.spy.togglePlay).toHaveBeenCalled();
    expect(space.event.defaultPrevented).toBe(true);
    const button = document.createElement("button");
    expect(press({ key: " " }, button).spy.togglePlay).not.toHaveBeenCalled();
    const slider = document.createElement("div");
    slider.setAttribute("role", "slider");
    expect(press({ key: " " }, slider).spy.togglePlay).not.toHaveBeenCalled();
  });

  it("clears the selection with Escape", () => {
    expect(press({ key: "Escape" }).spy.clearSelection).toHaveBeenCalled();
  });

  it("leaves keys typed in a text field alone", () => {
    const input = document.createElement("input");
    const typed = press({ key: "z", metaKey: true }, input);
    expect(typed.spy.undo).not.toHaveBeenCalled();
    expect(typed.event.defaultPrevented).toBe(false);
    expect(
      press({ key: "Backspace" }, input).spy.deleteSelection,
    ).not.toHaveBeenCalled();
  });

  it("ignores other keys with modifiers", () => {
    const { spy } = press({ key: " ", metaKey: true });
    expect(spy.togglePlay).not.toHaveBeenCalled();
    expect(
      press({ key: "Delete", altKey: true }).spy.deleteSelection,
    ).not.toHaveBeenCalled();
  });

  it("splits with S and zooms with + and -", () => {
    expect(press({ key: "s" }).spy.split).toHaveBeenCalled();
    expect(press({ key: "S" }).spy.split).toHaveBeenCalled();
    expect(press({ key: "+", shiftKey: true }).spy.zoom).toHaveBeenCalledWith(
      1,
    );
    expect(press({ key: "=" }).spy.zoom).toHaveBeenCalledWith(1);
    expect(press({ key: "-" }).spy.zoom).toHaveBeenCalledWith(-1);
    expect(press({ key: "s", metaKey: true }).spy.split).not.toHaveBeenCalled();
  });

  it("steps a frame with the arrows, 1 s with shift, unless on a slider", () => {
    const back = press({ key: "ArrowLeft" });
    expect(back.spy.step).toHaveBeenCalledWith(-1 / 30);
    expect(back.event.defaultPrevented).toBe(true);
    const forward = press({ key: "ArrowRight", shiftKey: true });
    expect(forward.spy.step).toHaveBeenCalledWith(1);

    const slider = document.createElement("div");
    slider.setAttribute("role", "slider");
    expect(press({ key: "ArrowLeft" }, slider).spy.step).not.toHaveBeenCalled();
  });
});
