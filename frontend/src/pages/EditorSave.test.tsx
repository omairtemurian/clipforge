import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Clip, Job } from "@/api/types";
import { FakeEventSource, mockEventSource } from "@/testing/fakeEventSource";
import { CLIP, mockLayoutAndMedia, renderEditor } from "@/testing/editor";
import { callsTo, json, project } from "@/testing/mockApi";

beforeEach(() => {
  mockLayoutAndMedia();
  mockEventSource();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const JOB: Job = {
  id: 5,
  project_id: 1,
  clip_id: 7,
  kind: "render",
  step: "render",
  progress: 0,
  status: "queued",
  error: null,
  log_path: "",
  priority: 0,
  attempts: 0,
  overall_progress: 0,
  eta_seconds: null,
};

/** PATCH /clips/7 answers the clip with the body applied. */
function patchRoute(): (url: string, init?: RequestInit) => Response {
  return (_url, init) => json({ ...CLIP, ...JSON.parse(String(init?.body)) });
}

async function openPanel(
  user: ReturnType<typeof userEvent.setup>,
  name: string,
) {
  await user.click(await screen.findByRole("button", { name }));
  return screen.getByRole("complementary", { name: `${name} panel` });
}

const saveButton = () => screen.getByRole("button", { name: "Save changes" });
const renderButton = () => screen.getByRole("button", { name: /^Render/ });

describe("text panel", () => {
  it("edits the texts, enforces their limits and saves them", async () => {
    const user = userEvent.setup();
    const fetchMock = renderEditor(undefined, undefined, {
      "PATCH /api/clips/7": patchRoute(),
    });
    const panel = await openPanel(user, "Text");
    expect(
      await screen.findByRole("button", { name: "Save changes" }),
    ).toBeDisabled();

    const title = within(panel).getByLabelText("Title");
    await user.clear(title);
    await user.click(title);
    await user.paste("x".repeat(80));
    expect(title).toHaveValue("x".repeat(70));
    expect(within(panel).getByText("70/70")).toBeVisible();

    const hook = within(panel).getByLabelText("Hook text");
    await user.clear(hook);
    await user.click(hook);
    await user.paste("y".repeat(65));
    expect(hook).toHaveValue("y".repeat(60));

    const description = within(panel).getByLabelText("Description");
    await user.clear(description);
    await user.click(description);
    await user.paste("z".repeat(320));
    expect(description).toHaveValue("z".repeat(300));

    const tags = within(panel).getByLabelText("Hashtags");
    await user.clear(tags);
    await user.type(tags, "#one, #two");
    expect(within(panel).getByRole("alert")).toHaveTextContent(
      "Use 3 to 8 hashtags (now 2).",
    );
    expect(saveButton()).toBeDisabled();
    expect(renderButton()).toBeDisabled();

    await user.type(tags, ", #three");
    expect(within(panel).queryByRole("alert")).toBe(null);
    await user.click(saveButton());

    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/clips/7")).toHaveLength(1),
    );
    const body = JSON.parse(
      String(callsTo(fetchMock, "PATCH", "/api/clips/7")[0][1]?.body),
    );
    expect(body).toMatchObject({
      title: "x".repeat(70),
      hook_text: "y".repeat(60),
      description: "z".repeat(300),
      hashtags: ["one", "two", "three"],
    });
    await waitFor(() => expect(saveButton()).toBeDisabled());
  });

  it("refuses more than 8 hashtags", async () => {
    const user = userEvent.setup();
    renderEditor();
    const panel = await openPanel(user, "Text");

    const tags = within(panel).getByLabelText("Hashtags");
    await user.clear(tags);
    await user.type(tags, "a b c d e f g h i");

    expect(within(panel).getByRole("alert")).toHaveTextContent("now 9");
    expect(saveButton()).toBeDisabled();
  });

  it("regenerates the title, description and hashtags with the LLM", async () => {
    const user = userEvent.setup();
    const regenerated: Clip = {
      ...CLIP,
      title: "A whole pizza",
      description: "He really ate it.",
      hashtags: ["pizza", "eating", "comedy", "wow"],
    };
    renderEditor(undefined, undefined, {
      "POST /api/clips/7/regenerate-text": () => json(regenerated),
    });
    const panel = await openPanel(user, "Text");

    await user.click(
      within(panel).getByRole("button", { name: "Regenerate with AI" }),
    );

    await waitFor(() =>
      expect(within(panel).getByLabelText("Title")).toHaveValue(
        "A whole pizza",
      ),
    );
    expect(within(panel).getByLabelText("Description")).toHaveValue(
      "He really ate it.",
    );
    expect(within(panel).getByLabelText("Hashtags")).toHaveValue(
      "#pizza #eating #comedy #wow",
    );
    // The server saved them, so only a later edit leaves something to save.
    expect(saveButton()).toBeDisabled();
    expect(within(panel).getByLabelText("Hook text")).toHaveValue(
      CLIP.hook_text,
    );
  });
});

describe("brand panel", () => {
  it("lists the brand templates and saves the choice for the project", async () => {
    const user = userEvent.setup();
    const brand = {
      id: 4,
      name: "Acme",
      logo_path: "/brand/4/logo.png",
      logo_position: "br",
      logo_opacity: 0.8,
      font: "Inter Bold",
      primary_color: "#FF6B35",
      intro_path: null,
      outro_path: null,
    };
    const fetchMock = renderEditor(undefined, undefined, {
      "GET /api/projects/1": () =>
        json(project({ id: 1, duration: 60, settings: {} as never })),
      "GET /api/brand-templates": () => json([brand]),
      "PATCH /api/projects/1": (_url, init) =>
        json(
          project({
            id: 1,
            duration: 60,
            settings: JSON.parse(String(init?.body)) as never,
          }),
        ),
    });
    const panel = await openPanel(user, "Brand");

    const select = within(panel).getByLabelText("Brand template");
    expect(select).toHaveValue("");
    await user.selectOptions(select, "Acme");

    await waitFor(() => expect(select).toHaveValue("4"));
    expect(
      JSON.parse(
        String(callsTo(fetchMock, "PATCH", "/api/projects/1")[0][1]?.body),
      ),
    ).toEqual({ brand_template_id: 4 });

    await user.selectOptions(select, "None");
    await waitFor(() => expect(select).toHaveValue(""));
  });
});

describe("render and download", () => {
  it("saves, renders with progress, then offers the download", async () => {
    const user = userEvent.setup();
    let status: Clip["status"] = "candidate";
    const fetchMock = renderEditor(undefined, undefined, {
      "GET /api/clips/7": () =>
        json({
          ...CLIP,
          status,
          output_path: status === "rendered" ? "/out/7.mp4" : null,
        }),
      "PATCH /api/clips/7": patchRoute(),
      "POST /api/clips/7/render": () => json(JOB, 202),
    });
    expect(
      screen.queryByRole("link", { name: "Download" }),
    ).not.toBeInTheDocument();
    const panel = await openPanel(user, "Text");
    await user.type(within(panel).getByLabelText("Hook text"), "!");

    await user.click(renderButton());

    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", "/api/clips/7/render")).toHaveLength(1),
    );
    const order = fetchMock.mock.calls
      .map(([, init]) => init?.method)
      .filter((method) => method === "PATCH" || method === "POST");
    expect(order).toEqual(["PATCH", "POST"]);

    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const events = FakeEventSource.instances[0];
    expect(events.url).toBe("/api/jobs/5/events");
    events.emit({
      step: "render",
      progress: 0.4,
      status: "running",
      message: "",
    });
    expect(
      await screen.findByRole("button", { name: "Rendering 40%" }),
    ).toBeDisabled();
    expect(screen.queryByRole("link", { name: "Download" })).toBe(null);

    status = "rendered";
    events.emit({ step: "render", progress: 1, status: "done", message: "" });

    const link = await screen.findByRole("link", { name: "Download" });
    expect(link).toHaveAttribute("href", "/api/clips/7/download");
    expect(renderButton()).toBeEnabled();
  });

  it("does not render when the save fails", async () => {
    const user = userEvent.setup();
    const fetchMock = renderEditor(undefined, undefined, {
      "PATCH /api/clips/7": () =>
        json(
          { error: "validation_error", message: "end is past the video" },
          422,
        ),
    });
    const panel = await openPanel(user, "Text");
    await user.type(within(panel).getByLabelText("Hook text"), "!");

    await user.click(renderButton());

    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/clips/7")).toHaveLength(1),
    );
    expect(callsTo(fetchMock, "POST", "/api/clips/7/render")).toHaveLength(0);
    expect(renderButton()).toBeEnabled();
  });

  it("shows a render that is already running and refuses a second one", async () => {
    renderEditor({ ...CLIP, status: "rendering" });

    expect(
      await screen.findByRole("button", { name: "Rendering…" }),
    ).toBeDisabled();
    expect(saveButton()).toBeDisabled();
  });
});
