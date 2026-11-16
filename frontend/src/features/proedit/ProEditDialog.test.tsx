import { QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createQueryClient } from "@/api/queryClient";
import type {
  ProEditChoices,
  ProEditEstimate,
  ProEditOptions,
} from "@/api/types";
import { FakeEventSource, mockEventSource } from "@/testing/fakeEventSource";
import { clip, json, mockApi, project } from "@/testing/mockApi";
import { CHOICES, estimate, proEditRun } from "@/testing/proeditFixtures";
import { ProEditDialog } from "./ProEditDialog";

const ORIGINAL = clip({ id: 7, title: "Pizza night", status: "rendered" });
const VARIANT = {
  ...ORIGINAL,
  id: 12,
  title: "Pizza night — Pro Edit",
  parent_clip_id: 7,
  variant: "pro_edit" as const,
  status: "rendering" as const,
};

/** The Pro Edit API of clip 7 with choices and an estimate answer. */
const RUN_NOTES = [
  "The critic is off (proedit.critic_max_rounds is 0).",
  "Dropped zoom_punch at 15.93 s: over the standard budget of 1 zoom_punch per 3 s",
];

function api(
  choices: ProEditChoices = CHOICES,
  answer: ProEditEstimate = estimate(),
) {
  return mockApi((url, init) => {
    const method = init?.method ?? "GET";
    if (url === "/api/proedit/status") {
      return json({ enabled: true, critic_max_rounds: 2 });
    }
    if (url === "/api/proedit/clips/7/choices") return json(choices);
    if (url.startsWith("/api/proedit/clips/7/estimate?")) return json(answer);
    if (url === "/api/projects/1") return json(project({ id: 1 }));
    if (url === "/api/proedit/clips/12/runs") {
      return json([{ ...proEditRun(), status: "done", notes: RUN_NOTES }]);
    }
    if (method === "POST" && url === "/api/proedit/clips/7/runs") {
      const options = JSON.parse(String(init?.body)) as ProEditOptions;
      return json({ clip: VARIANT, run: proEditRun(options), job_id: 77 }, 202);
    }
    return json({ error: "not_found", message: `no route ${url}` }, 404);
  });
}

function renderDialog(onClose = vi.fn()) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <ProEditDialog clip={ORIGINAL} onClose={onClose} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return onClose;
}

/** The URLs of the estimate requests fetchMock got. */
function estimateUrls(fetchMock: ReturnType<typeof api>): string[] {
  return fetchMock.mock.calls
    .map(([url]) => url)
    .filter((url) => url.includes("/estimate?"));
}

beforeEach(() => mockEventSource());

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Pro Edit dialog", () => {
  it("runs the picked options and follows the run's progress", async () => {
    const user = userEvent.setup();
    const fetchMock = api();
    renderDialog();

    const presets = await screen.findAllByRole("radio");
    expect(presets).toHaveLength(6);
    expect(screen.getByRole("radio", { name: /Clean Pro/ })).toBeChecked();
    expect(
      await screen.findByText("About $0.04 with the critic (2 rounds)."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: /Phonk Edit/ }));
    fireEvent.change(screen.getByRole("slider", { name: /Intensity/ }), {
      target: { value: "3" },
    });
    await user.selectOptions(screen.getByLabelText("Style recipe"), "3");
    await user.selectOptions(screen.getByLabelText("Music"), "42");
    await user.click(screen.getByRole("switch", { name: "Use critic" }));
    await user.click(
      screen.getByRole("switch", { name: "Loop-friendly ending" }),
    );
    await user.click(
      screen.getByRole("switch", { name: "Subject in front of text" }),
    );
    expect(screen.queryByLabelText("Background color")).toBeNull();
    await user.selectOptions(screen.getByLabelText("Background"), "swap");
    fireEvent.change(screen.getByLabelText("Background color"), {
      target: { value: "#00ff88" },
    });

    await waitFor(() =>
      expect(estimateUrls(fetchMock).at(-1)).toBe(
        "/api/proedit/clips/7/estimate?preset=phonk_edit&intensity=extreme&music=42&use_critic=false&loop_ending=true&style_recipe_id=3",
      ),
    );
    await user.click(screen.getByRole("button", { name: "Run Pro Edit" }));

    const post = fetchMock.mock.calls.find(
      ([url, init]) =>
        url === "/api/proedit/clips/7/runs" && init?.method === "POST",
    );
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      preset: "phonk_edit",
      intensity: "extreme",
      style_recipe_id: 3,
      music: "42",
      use_critic: false,
      loop_ending: true,
      subject_front: true,
      background: "swap",
      background_color: "#00ff88",
    });
    const steps = await screen.findByRole("list", { name: "Pro Edit steps" });
    expect(
      within(steps)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(["Plan", "Final render"]);
    expect(
      screen.getByRole("link", { name: /Open Pro Edit variants/ }),
    ).toHaveAttribute("href", "/clips/7/proedit?variant=12");
  });

  it("shows plan, proxy, critic round n/N and final from the job events", async () => {
    const user = userEvent.setup();
    api();
    renderDialog();
    await user.click(
      await screen.findByRole("button", { name: "Run Pro Edit" }),
    );
    const steps = await screen.findByRole("list", { name: "Pro Edit steps" });
    const source = FakeEventSource.instances.at(-1);
    expect(source?.url).toBe("/api/jobs/77/events");

    act(() =>
      source?.emit({
        step: "critic",
        progress: 0.5,
        status: "running",
        message: "",
        overall_progress: 0.6,
        eta_seconds: 120,
      }),
    );

    const items = within(steps).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      "Plan",
      "Proxy",
      "Critic round 2/2",
      "Final render",
    ]);
    expect(items.map((item) => item.dataset.state)).toEqual([
      "done",
      "done",
      "running",
      "pending",
    ]);
    expect(
      screen.getByRole("progressbar", { name: "Pro Edit progress" }),
    ).toHaveAttribute("aria-valuenow", "60");
    expect(screen.getByText("60% · ETA 2m")).toBeInTheDocument();

    act(() =>
      source?.emit({
        step: "final",
        progress: 1,
        status: "done",
        message: "",
        overall_progress: 1,
      }),
    );
    expect(
      await screen.findByText(/The Pro Edit variant is ready/),
    ).toBeInTheDocument();
    const notes = await screen.findByRole("region", { name: "Edit notes" });
    expect(within(notes).getAllByRole("listitem")).toHaveLength(1);
    expect(notes).toHaveTextContent(
      "DroppedZoom punch15.93 sover the standard budget of 1 zoom_punch per 3 s",
    );
  });

  it("caps the intensity and warns about the campaign's heavy-edit rule", async () => {
    api({
      ...CHOICES,
      campaign_id: 1,
      campaign_name: "Pizza Clips",
      allow_heavy_edits: "false",
      max_intensity: "pro",
    });
    renderDialog();

    expect(
      await screen.findByText(/Pizza Clips does not allow heavy edits/),
    ).toBeInTheDocument();
    const slider = screen.getByRole("slider", { name: /Intensity/ });
    expect(slider).toHaveAttribute("max", "2");
    fireEvent.change(slider, { target: { value: "2" } });
    expect(slider).toHaveAttribute("aria-valuetext", "Pro");
    expect(
      screen.getByText("The campaign's autopilot caps Pro Edit at Pro."),
    ).toBeInTheDocument();
  });

  it("blocks Run while the monthly LLM cap is used up", async () => {
    api(CHOICES, estimate({ blocked: true, text: "About $0.04." }));
    renderDialog();

    expect(
      await screen.findByText("About $0.04. The monthly LLM cap is used up."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run Pro Edit" })).toBeDisabled();
  });

  it("closes with Cancel", async () => {
    const user = userEvent.setup();
    api();
    const onClose = renderDialog();

    await user.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(onClose).toHaveBeenCalled();
  });

  it("scrolls the options and keeps Cancel and Run outside them", async () => {
    api();
    renderDialog();

    const options = await screen.findByRole("group", {
      name: "Pro Edit options",
    });
    expect(options).toHaveClass("min-h-0", "overflow-y-auto");
    expect(within(options).getAllByRole("radio")).toHaveLength(6);
    for (const name of ["Cancel", "Run Pro Edit"]) {
      expect(options).not.toContainElement(
        screen.getByRole("button", { name }),
      );
    }
  });
});
