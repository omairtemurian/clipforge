import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { clearToasts } from "@/lib/toast";
import { json, mockApi } from "@/testing/mockApi";
import { forgetUpload, sha256Hex, uploadInChunks } from "./chunkedUpload";

const ID = "a".repeat(32);

/**
 * An in-memory /api/uploads that checks offsets and checksums like the real
 * one. The next `dropPatches` PATCHes fail as a dropped connection.
 */
function fakeServer(size: number, start = 0) {
  const state = { offset: start, dropPatches: 0, patches: [] as number[] };
  const session = () => ({
    id: ID,
    filename: "talk.mp4",
    size,
    offset: state.offset,
  });
  const fetchMock = mockApi(async (url, init) => {
    const method = init?.method ?? "GET";
    if (method === "POST" && url === "/api/uploads")
      return json(session(), 201);
    if (method === "GET" && url === `/api/uploads/${ID}`)
      return json(session());
    if (method === "PATCH") {
      const offset = Number(
        new URL(url, "http://x").searchParams.get("offset"),
      );
      state.patches.push(offset);
      if (state.dropPatches > 0) {
        state.dropPatches -= 1;
        throw new TypeError("Failed to fetch");
      }
      if (offset !== state.offset) {
        return json({ error: "offset_mismatch", message: "offset" }, 409);
      }
      const body = init?.body as ArrayBuffer;
      const sha = new Headers(init?.headers).get("X-Chunk-SHA256");
      if (sha !== (await sha256Hex(body))) {
        return json({ error: "checksum_mismatch", message: "sha" }, 422);
      }
      state.offset += body.byteLength;
      return json(session());
    }
    return json({ error: "not_found", message: url }, 404);
  });
  return { state, fetchMock };
}

const file = new File(["0123456789abcdefghij"], "talk.mp4", {
  lastModified: 1,
});

beforeEach(() => localStorage.clear());
afterEach(() => act(() => clearToasts()));

describe("uploadInChunks", () => {
  it("sends the file in checksummed chunks and reports progress", async () => {
    const { state } = fakeServer(file.size);
    const progress: number[] = [];

    const id = await uploadInChunks(file, {
      chunkBytes: 8,
      onProgress: (sent) => progress.push(sent),
    });

    expect(id).toBe(ID);
    expect(state.patches).toEqual([0, 8, 16]);
    expect(progress).toEqual([0, 8, 16, 20]);
  });

  it("resumes a remembered upload from the offset the server reports", async () => {
    const first = fakeServer(file.size);
    first.state.dropPatches = 1;
    await expect(uploadInChunks(file, { attempts: 1 })).rejects.toThrow();
    const { state, fetchMock } = fakeServer(file.size, 12);

    await uploadInChunks(file, { chunkBytes: 8 });

    expect(state.patches).toEqual([12]);
    expect(
      fetchMock.mock.calls.some(([, init]) => init?.method === "POST"),
    ).toBe(false);
  });

  it("re-reads the offset and resends after a dropped connection", async () => {
    const { state } = fakeServer(file.size);
    state.dropPatches = 1;

    await uploadInChunks(file, { chunkBytes: 8, retryDelayMs: 0 });

    expect(state.patches).toEqual([0, 0, 8, 16]);
    expect(state.offset).toBe(20);
  });

  it("gives up after the allowed failures in a row", async () => {
    const { state } = fakeServer(file.size);
    state.dropPatches = Infinity;

    await expect(
      uploadInChunks(file, { chunkBytes: 8, attempts: 3, retryDelayMs: 0 }),
    ).rejects.toMatchObject({ code: "network_error" });
    expect(state.patches).toEqual([0, 0, 0]);
  });

  it("starts a new session after forgetUpload", async () => {
    fakeServer(file.size);
    await uploadInChunks(file, { chunkBytes: 20 });
    forgetUpload(file);
    const { fetchMock } = fakeServer(file.size);

    await uploadInChunks(file, { chunkBytes: 20 });

    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
  });
});
