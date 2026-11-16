import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "@/components/Toaster";
import { clearToasts, dismissToast } from "@/lib/toast";
import { ApiError, apiFetch, apiUrl } from "./client";

function respond(status: number, body: unknown, init: ResponseInit = {}) {
  const payload = typeof body === "string" ? body : JSON.stringify(body);
  return new Response(status === 204 ? null : payload, { status, ...init });
}

function mockFetch(response: Response | Error) {
  const fetchMock = vi.fn(() =>
    response instanceof Error
      ? Promise.reject(response)
      : Promise.resolve(response),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  act(() => clearToasts());
});

describe("apiFetch", () => {
  it("returns the parsed JSON and prefixes /api", async () => {
    const fetchMock = mockFetch(respond(200, { id: 3 }));

    await expect(apiFetch("/projects/3")).resolves.toEqual({ id: 3 });
    expect(fetchMock.mock.calls[0]).toEqual([
      "/api/projects/3",
      expect.objectContaining({ headers: expect.any(Headers) }),
    ]);
    expect(apiUrl("/clips/1/video")).toBe("/api/clips/1/video");
  });

  it("sends json bodies with a content type", async () => {
    const fetchMock = mockFetch(respond(200, {}));

    await apiFetch("/projects", { method: "POST", json: { url: "x" } });

    const init = (fetchMock.mock.calls[0] as unknown[])[1] as RequestInit;
    expect(init.body).toBe('{"url":"x"}');
    expect((init.headers as Headers).get("Content-Type")).toBe(
      "application/json",
    );
  });

  it("returns undefined for 204", async () => {
    mockFetch(respond(204, null));
    await expect(apiFetch("/clips/1", { method: "DELETE" })).resolves.toBe(
      undefined,
    );
  });

  it("throws an ApiError with the server message and shows a toast", async () => {
    mockFetch(
      respond(404, { error: "not_found", message: "project 9 not found" }),
    );
    const user = userEvent.setup();
    render(<Toaster />);

    const failure = await apiFetch("/projects/9").catch((e: unknown) => e);

    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({
      status: 404,
      code: "not_found",
      message: "project 9 not found",
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "project 9 not found",
    );

    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("does not toast when silent", async () => {
    mockFetch(respond(409, { error: "conflict", message: "already exists" }));
    render(<Toaster />);

    await expect(apiFetch("/x", { silent: true })).rejects.toThrow(
      "already exists",
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("falls back to the status line when the body is not JSON", async () => {
    mockFetch(
      respond(502, "<html>bad gateway</html>", { statusText: "Bad Gateway" }),
    );

    await expect(apiFetch("/x", { silent: true })).rejects.toMatchObject({
      status: 502,
      code: "http_error",
      message: "Request failed (502 Bad Gateway)",
    });
  });

  it("reports a network failure as an ApiError", async () => {
    mockFetch(new TypeError("Failed to fetch"));

    await expect(apiFetch("/x", { silent: true })).rejects.toMatchObject({
      status: 0,
      code: "network_error",
    });
  });
});

describe("toast store", () => {
  it("dismisses an unknown id without error", () => {
    expect(() => dismissToast(-1)).not.toThrow();
  });
});
