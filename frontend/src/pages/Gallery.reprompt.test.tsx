import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type { Chapter, Project } from "@/api/types";
import {
  callsTo,
  job,
  json,
  mockRoutes,
  project,
  scored,
} from "@/testing/mockApi";
import { Gallery } from "./Gallery";

const CHAPTERS: Chapter[] = [
  { id: 1, start: 0, end: 600, title: "Intro", summary: "Who we are." },
  { id: 2, start: 600, end: 1500, title: "Pricing", summary: "What it costs." },
];

function renderGallery(overrides: Partial<Project> = {}) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <Gallery project={project({ id: 1, ...overrides })} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function api(chapters: Chapter[] = CHAPTERS) {
  let made = chapters;
  return mockRoutes({
    "GET /api/campaigns": () => json([]),
    "GET /api/projects/1/clips": () => json([scored(2, 80, "Newest set")]),
    "GET /api/projects/1/clips?result_set=1": () =>
      json([scored(1, 90, "First set")]),
    "GET /api/projects/1/chapters": () => json(made),
    "POST /api/projects/1/chapters": () => {
      made = CHAPTERS;
      return json(CHAPTERS);
    },
    "POST /api/projects/1/reprompt": () => json(job({ kind: "reprompt" })),
    "POST /api/projects/1/clip-by-topic": () => json(job({ kind: "reprompt" })),
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Gallery reprompt", () => {
  it("sends the new prompt and closes the dialog", async () => {
    const fetchMock = api();
    renderGallery({
      settings: { keyword_prompt: "old request" } as Project["settings"],
    });
    await screen.findByText("Newest set");

    await userEvent.click(screen.getByRole("button", { name: "Reprompt" }));
    const box = screen.getByLabelText("Find moments about");
    expect(box).toHaveValue("old request");
    await userEvent.clear(box);
    expect(screen.getByRole("button", { name: "Find clips" })).toBeDisabled();
    await userEvent.type(box, "  funny fails ");
    await userEvent.click(screen.getByRole("button", { name: "Find clips" }));

    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    const [[, init]] = callsTo(fetchMock, "POST", "/api/projects/1/reprompt");
    expect(JSON.parse(String(init?.body))).toEqual({ prompt: "funny fails" });
  });

  it("shows the previous result set when one is chosen", async () => {
    api();
    renderGallery({ result_set: 2 });
    await screen.findByText("Newest set");

    await userEvent.selectOptions(screen.getByLabelText("Result"), "1");

    expect(await screen.findByText("First set")).toBeInTheDocument();
  });

  it("has no result chooser while there is one set", async () => {
    api();
    renderGallery();
    await screen.findByText("Newest set");

    expect(screen.queryByLabelText("Result")).not.toBeInTheDocument();
  });
});

describe("Gallery topics", () => {
  it("lists the topics and clips the chosen ones with a prompt", async () => {
    const fetchMock = api();
    renderGallery();
    await screen.findByText("Newest set");

    await userEvent.click(screen.getByRole("button", { name: "Topics" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Intro")).toBeInTheDocument();
    expect(within(dialog).getByText("10:00 – 25:00")).toBeInTheDocument();
    const clipButton = within(dialog).getByRole("button", {
      name: "Clip selected topics",
    });
    expect(clipButton).toBeDisabled();

    await userEvent.click(within(dialog).getByLabelText("Pricing"));
    await userEvent.type(
      within(dialog).getByLabelText("Find moments about (optional)"),
      "discounts",
    );
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Clip selected topics (1)" }),
    );

    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    const [[, init]] = callsTo(
      fetchMock,
      "POST",
      "/api/projects/1/clip-by-topic",
    );
    expect(JSON.parse(String(init?.body))).toEqual({
      chapters: [2],
      prompt: "discounts",
    });
  });

  it("makes the topics when there are none", async () => {
    const fetchMock = api([]);
    renderGallery();
    await screen.findByText("Newest set");

    await userEvent.click(screen.getByRole("button", { name: "Topics" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/No topics yet/)).toBeVisible();
    expect(
      within(dialog).queryByRole("button", { name: /Clip selected/ }),
    ).not.toBeInTheDocument();

    await userEvent.click(
      within(dialog).getByRole("button", { name: "Find topics" }),
    );

    expect(await within(dialog).findByText("Pricing")).toBeInTheDocument();
    expect(callsTo(fetchMock, "POST", "/api/projects/1/chapters")).toHaveLength(
      1,
    );
  });
});
