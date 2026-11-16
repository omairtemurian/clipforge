import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  AUTOSAVE_DELAY_MS,
  useAutosave,
  type AutosaveInput,
} from "./useAutosave";

beforeEach(() => {
  vi.useFakeTimers();
  window.localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

function renderAutosave(initial: Partial<AutosaveInput>) {
  const save = vi.fn(() => Promise.resolve(true));
  const props: AutosaveInput = {
    dirty: true,
    edits: "a",
    blocked: false,
    saving: false,
    save,
    ...initial,
  };
  const hook = renderHook((input: AutosaveInput) => useAutosave(input), {
    initialProps: props,
  });
  return { ...hook, save: props.save as typeof save, props };
}

describe("useAutosave", () => {
  it("saves once the edits have rested for the delay", async () => {
    const { result, save, rerender, props } = renderAutosave({});
    expect(result.current.status).toBe("pending");
    await act(() => vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS - 100));
    rerender({ ...props, edits: "b" });
    await act(() => vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS - 100));
    expect(save).not.toHaveBeenCalled();

    await act(() => vi.advanceTimersByTimeAsync(100));
    expect(save).toHaveBeenCalledTimes(1);
  });

  it("does not save clean, blocked or turned-off edits", async () => {
    const clean = renderAutosave({ dirty: false });
    const blocked = renderAutosave({ blocked: true });
    await act(() => vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS * 2));
    expect(clean.save).not.toHaveBeenCalled();
    expect(clean.result.current.status).toBe("saved");
    expect(blocked.save).not.toHaveBeenCalled();

    const off = renderAutosave({});
    act(() => off.result.current.toggle());
    await act(() => vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS * 2));
    expect(off.save).not.toHaveBeenCalled();
    expect(off.result.current.status).toBe("off");
    expect(window.localStorage.getItem("clipforge.autosave")).toBe("off");
    expect(renderAutosave({}).result.current.on).toBe(false);
  });

  it("does not retry a failed save until the edits change", async () => {
    const save = vi.fn(() => Promise.resolve(false));
    const { result, rerender, props } = renderAutosave({ save });
    await act(() => vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS));
    expect(result.current.status).toBe("failed");
    await act(() => vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS * 3));
    expect(save).toHaveBeenCalledTimes(1);

    rerender({ ...props, edits: "b" });
    await act(() => vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS));
    expect(save).toHaveBeenCalledTimes(2);
  });

  it("reports saving while a save is under way", () => {
    const { result } = renderAutosave({ saving: true, blocked: true });
    expect(result.current.status).toBe("saving");
  });
});
