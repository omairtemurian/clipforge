import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { Post } from "@/api/types";
import { callsTo, clip, json, mockRoutes } from "@/testing/mockApi";
import { localIso, post, socialAccount } from "@/testing/postFixtures";
import { PostEditor } from "./PostEditor";

afterEach(() => vi.unstubAllGlobals());

function renderEditor(shown: Post, onClose = vi.fn()) {
  const fetchMock = mockRoutes({
    "GET /api/clips/7": () => json(clip({ id: 7 })),
    "PATCH /api/posts/1": () => json(shown),
    "POST /api/posts/1/cancel": () => json({ ...shown, status: "canceled" }),
    "POST /api/posts/1/queue": () => json({ ...shown, status: "queued" }),
  });
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <PostEditor
          post={shown}
          account={socialAccount({ display_name: "Main channel" })}
          onClose={onClose}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { fetchMock, onClose };
}

function bodyOf(call: [string, RequestInit?]): unknown {
  return JSON.parse(String(call[1]?.body));
}

const SCHEDULED = post({
  scheduled_at: localIso(2030, 1, 14, 8),
  payload: {
    title: "Pizza night",
    description: "A man and a whole pizza.",
    text: { title: "Pizza night!" },
  },
});

describe("PostEditor", () => {
  it("saves only the text fields the user changed", async () => {
    const user = userEvent.setup();
    const { fetchMock } = renderEditor(SCHEDULED);

    expect(
      screen.getByRole("dialog", { name: "Pizza night" }),
    ).toHaveAccessibleDescription("Main channel · YouTube");
    expect(screen.getByRole("link", { name: "Open clip" })).toHaveAttribute(
      "href",
      "/clips/7",
    );
    const title = await screen.findByLabelText("Title");
    expect(title).toHaveValue("Pizza night!");
    expect(screen.getByLabelText("Description")).toHaveValue(
      "A man and a whole pizza.",
    );

    await user.clear(title);
    await user.type(title, "Whole pizza");
    await user.click(screen.getByRole("button", { name: "Save text" }));

    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/posts/1")).toHaveLength(1),
    );
    expect(
      bodyOf(callsTo(fetchMock, "PATCH", "/api/posts/1")[0]),
    ).toMatchObject({
      text: { title: "Whole pizza", caption: null, hashtags: null },
    });
  });

  it("reschedules to the picked time", async () => {
    const user = userEvent.setup();
    const { fetchMock } = renderEditor(SCHEDULED);
    const at = screen.getByLabelText("Publish at");

    expect(at).toHaveValue("2030-01-14T08:00");
    await user.clear(at);
    await user.type(at, "2030-01-15T19:45");
    await user.click(screen.getByRole("button", { name: "Reschedule" }));

    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/posts/1")).toHaveLength(1),
    );
    expect(bodyOf(callsTo(fetchMock, "PATCH", "/api/posts/1")[0])).toEqual({
      scheduled_at: localIso(2030, 1, 15, 19, 45),
    });
  });

  it("cancels only after the user confirms", async () => {
    const user = userEvent.setup();
    const { fetchMock, onClose } = renderEditor(SCHEDULED);

    await user.click(screen.getByRole("button", { name: "Cancel post" }));
    expect(
      screen.getByText("Cancel this post? It will not go out."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Keep" }));
    expect(callsTo(fetchMock, "POST", "/api/posts/1/cancel")).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Cancel post" }));
    await user.click(screen.getByRole("button", { name: "Yes, cancel post" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(callsTo(fetchMock, "POST", "/api/posts/1/cancel")).toHaveLength(1);
  });

  it("schedules a timed draft", async () => {
    const user = userEvent.setup();
    const { fetchMock } = renderEditor({ ...SCHEDULED, status: "draft" });

    await user.click(screen.getByRole("button", { name: "Schedule post" }));
    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", "/api/posts/1/queue")).toHaveLength(1),
    );
  });

  it("shows a failed post's error without edit controls", () => {
    renderEditor({ ...SCHEDULED, status: "failed", error: "Token expired." });

    expect(screen.getByRole("alert")).toHaveTextContent("Token expired.");
    expect(screen.getByText(/^Tried /)).toBeInTheDocument();
    expect(screen.queryByLabelText("Publish at")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Cancel post" }),
    ).not.toBeInTheDocument();
  });
});
