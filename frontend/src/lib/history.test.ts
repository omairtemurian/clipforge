import { describe, expect, it } from "vitest";
import {
  HISTORY_LIMIT,
  historyReducer,
  initHistory,
  type History,
  type HistoryAction,
} from "./history";

type Value = { start: number; cuts: [number, number][] };

function run(
  actions: HistoryAction<Value>[],
  state: History<Value> = initHistory({ start: 0, cuts: [] }),
) {
  return actions.reduce(historyReducer<Value>, state);
}

const set = (start: number, gesture?: number): HistoryAction<Value> => ({
  type: "set",
  value: { start, cuts: [] },
  gesture,
});

describe("undo/redo reducer", () => {
  it("starts with nothing to undo or redo", () => {
    expect(initHistory(5)).toEqual({
      past: [],
      present: 5,
      future: [],
      gesture: null,
    });
  });

  it("undoes and redoes changes in order", () => {
    const state = run([set(1), set(2), set(3)]);
    expect(state.past.map((v) => v.start)).toEqual([0, 1, 2]);

    const undone = run([{ type: "undo" }, { type: "undo" }], state);
    expect(undone.present.start).toBe(1);
    expect(undone.future.map((v) => v.start)).toEqual([2, 3]);

    const redone = run([{ type: "redo" }], undone);
    expect(redone.present.start).toBe(2);
    expect(redone.past.map((v) => v.start)).toEqual([0, 1]);
    expect(redone.future.map((v) => v.start)).toEqual([3]);
  });

  it("forgets the undone changes after a new change", () => {
    const state = run([set(1), set(2), { type: "undo" }, set(7)]);
    expect(state.present.start).toBe(7);
    expect(state.future).toEqual([]);
    expect(run([{ type: "redo" }], state)).toBe(state);
  });

  it("does nothing without a step to undo or redo", () => {
    const state = run([]);
    expect(run([{ type: "undo" }], state)).toBe(state);
    expect(run([{ type: "redo" }], state)).toBe(state);
  });

  it("ignores a change to the same value", () => {
    const state = run([set(1)]);
    expect(run([set(1)], state)).toBe(state);
    expect(run([{ type: "set", value: { start: 1, cuts: [] } }], state)).toBe(
      state,
    );
  });

  it("makes one step of all changes of a gesture", () => {
    const state = run([set(1), set(2, 9), set(3, 9), set(4, 9)]);
    expect(state.present.start).toBe(4);
    expect(state.past.map((v) => v.start)).toEqual([0, 1]);
    expect(run([{ type: "undo" }], state).present.start).toBe(1);

    const next = run([set(5, 10), set(6)], state);
    expect(next.past.map((v) => v.start)).toEqual([0, 1, 4, 5]);
  });

  it("starts a new step for a gesture after an undo", () => {
    const state = run([
      set(1, 3),
      { type: "undo" },
      { type: "redo" },
      set(2, 3),
    ]);
    expect(state.past.map((v) => v.start)).toEqual([0, 1]);
  });

  it(`keeps at most ${HISTORY_LIMIT} steps to undo`, () => {
    const changes = Array.from({ length: HISTORY_LIMIT + 5 }, (_, i) =>
      set(i + 1),
    );
    const state = run(changes);
    expect(state.past).toHaveLength(HISTORY_LIMIT);
    expect(state.past[0].start).toBe(5);
  });

  it("resets to a value with no history", () => {
    const state = run([
      set(1),
      set(2),
      { type: "reset", value: { start: 9, cuts: [] } },
    ]);
    expect(state).toEqual(initHistory({ start: 9, cuts: [] }));
  });
});
