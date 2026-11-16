import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { Clip, ClipHistory } from "@/api/types";
import { callsTo, clip, json, mockRoutes } from "@/testing/mockApi";
import { useClipEdits } from "./useClipEdits";
import { redoTarget, undoTarget, useUndo, type UndoState } from "./useUndo";

afterEach(() => {
  vi.unstubAllGlobals();
});

const CLIP = clip({ id: 7, start: 10, end: 40, cut_ranges: [] });
const EARLIER: Clip = { ...CLIP, start: 12, end: 30 };

function history(overrides: Partial<ClipHistory> = {}): ClipHistory {
  return {
    current: 2,
    can_undo: true,
    can_redo: false,
    versions: [
      {
        number: 1,
        kind: "original",
        created_at: "2026-11-01T20:00:00",
        fields: [],
        restored_from: null,
      },
      {
        number: 2,
        kind: "edit",
        created_at: "2026-11-01T20:05:00",
        fields: ["segments"],
        restored_from: null,
      },
    ],
    ...overrides,
  };
}

function state(overrides: Partial<UndoState>): UndoState {
  return {
    dirty: false,
    canUndoLocal: false,
    canRedoLocal: false,
    history: history(),
    busy: false,
    ...overrides,
  };
}

describe("undoTarget / redoTarget", () => {
  it("undoes unsaved edits locally, saved ones on the server", () => {
    expect(undoTarget(state({ dirty: true, canUndoLocal: true }))).toBe(
      "local",
    );
    expect(undoTarget(state({ dirty: true }))).toBeNull();
    expect(undoTarget(state({ canUndoLocal: true }))).toBe("server");
  });

  it("stays local without a history, or while busy", () => {
    expect(undoTarget(state({ history: undefined, canUndoLocal: true }))).toBe(
      "local",
    );
    expect(undoTarget(state({ busy: true, canUndoLocal: true }))).toBe("local");
    expect(undoTarget(state({ busy: true }))).toBeNull();
    const first = history({ can_undo: false });
    expect(undoTarget(state({ history: first }))).toBeNull();
  });

  it("redoes a local undo first, then a server undo of a saved clip", () => {
    const undone = history({ can_redo: true });
    expect(redoTarget(state({ canRedoLocal: true, history: undone }))).toBe(
      "local",
    );
    expect(redoTarget(state({ history: undone }))).toBe("server");
    expect(redoTarget(state({ history: undone, dirty: true }))).toBeNull();
    expect(redoTarget(state({}))).toBeNull();
  });
});

/** useUndo over useClipEdits(CLIP) with the API answering routes. */
function renderUndo(routes: Parameters<typeof mockRoutes>[0]) {
  const fetchMock = mockRoutes(routes);
  const client = createQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
  const { result } = renderHook(
    () => {
      const edits = useClipEdits(CLIP);
      return { edits, undo: useUndo(7, edits, false) };
    },
    { wrapper },
  );
  return { result, fetchMock };
}

describe("useUndo", () => {
  it("undoes an unsaved edit locally without calling the API", async () => {
    const { result, fetchMock } = renderUndo({
      "GET /api/clips/7/versions": () => json(history()),
    });
    await waitFor(() => expect(result.current.undo.history).toBeDefined());
    act(() => result.current.edits.setRange({ start: 11, end: 40 }));
    expect(result.current.undo.canUndo).toBe(true);

    act(() => result.current.undo.undo());

    expect(result.current.edits.range).toEqual({ start: 10, end: 40 });
    expect(callsTo(fetchMock, "POST", "/api/clips/7/undo")).toHaveLength(0);
  });

  it("undoes a saved clip on the server and starts over from its answer", async () => {
    const { result, fetchMock } = renderUndo({
      "GET /api/clips/7/versions": () => json(history()),
      "POST /api/clips/7/undo": () => json(EARLIER),
    });
    await waitFor(() => expect(result.current.undo.canUndo).toBe(true));

    act(() => result.current.undo.undo());

    await waitFor(() =>
      expect(result.current.edits.range).toEqual({ start: 12, end: 30 }),
    );
    expect(callsTo(fetchMock, "POST", "/api/clips/7/undo")).toHaveLength(1);
    expect(result.current.edits.canUndo).toBe(false);
  });

  it("redoes on the server once nothing is left to redo locally", async () => {
    const { result, fetchMock } = renderUndo({
      "GET /api/clips/7/versions": () =>
        json(history({ can_undo: false, can_redo: true })),
      "POST /api/clips/7/redo": () => json(EARLIER),
    });
    await waitFor(() => expect(result.current.undo.canRedo).toBe(true));
    expect(result.current.undo.canUndo).toBe(false);

    act(() => result.current.undo.redo());

    await waitFor(() =>
      expect(result.current.edits.range).toEqual({ start: 12, end: 30 }),
    );
    expect(callsTo(fetchMock, "POST", "/api/clips/7/redo")).toHaveLength(1);
  });

  it("restores a version and reloads the history", async () => {
    const { result, fetchMock } = renderUndo({
      "GET /api/clips/7/versions": () => json(history()),
      "POST /api/clips/7/versions/1/restore": () => json(EARLIER),
    });
    await waitFor(() => expect(result.current.undo.history).toBeDefined());

    let done = false;
    await act(async () => {
      done = await result.current.undo.restore(1);
    });

    expect(done).toBe(true);
    expect(result.current.edits.range).toEqual({ start: 12, end: 30 });
    await waitFor(() =>
      expect(callsTo(fetchMock, "GET", "/api/clips/7/versions")).toHaveLength(
        2,
      ),
    );
  });

  it("works without a history: a failed load leaves local undo", async () => {
    const { result } = renderUndo({});
    act(() => result.current.edits.setRange({ start: 11, end: 40 }));
    act(() => result.current.edits.setRange({ start: 11, end: 39 }));
    await waitFor(() => expect(result.current.undo.history).toBeUndefined());

    act(() => result.current.undo.undo());

    expect(result.current.edits.range).toEqual({ start: 11, end: 40 });
  });
});
