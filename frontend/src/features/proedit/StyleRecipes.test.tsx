import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { StyleRecipeDetail, StyleRecipeExport } from "@/api/types";
import { mockEventSource } from "@/testing/fakeEventSource";
import { mockLayoutAndMedia, renderAt } from "@/testing/editor";
import { callsTo, json, type Handler } from "@/testing/mockApi";
import { DETAIL, METRICS, RECIPE } from "@/testing/styleRecipeFixtures";

beforeEach(() => {
  mockLayoutAndMedia();
  mockEventSource();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const API = "/api/proedit/style-recipes";
const TERMS = {
  notice: "Downloading videos may break the site's terms.",
  max_links: 5,
  max_seconds: 180,
  max_height: 720,
};

/** Open the style recipes page at path with recipe 3 stored. */
function open(path = "/proedit/style-recipes?recipe=3", routes = {}) {
  const fetchMock = renderAt(path, {
    "GET /api/proedit/status": () => json({ enabled: true }),
    [`GET ${API}`]: () => json([RECIPE]),
    [`GET ${API}/3`]: () => json(DETAIL),
    [`GET ${API}/metrics`]: () => json(METRICS),
    [`GET ${API}/terms`]: () => json(TERMS),
    ...routes,
  } satisfies Record<string, Handler>);
  return fetchMock;
}

function bodyOf(
  fetchMock: ReturnType<typeof open>,
  method: string,
  url: string,
) {
  return JSON.parse(
    String(callsTo(fetchMock, method, url)[0][1]?.body),
  ) as unknown;
}

describe("Style recipes page", () => {
  it("edits a recipe's targets with sliders and saves them", async () => {
    const user = userEvent.setup();
    const saved: StyleRecipeDetail = {
      ...DETAIL,
      recipe: { ...RECIPE, name: "Faster phonk" },
    };
    const fetchMock = open("/proedit/style-recipes?recipe=3", {
      [`PATCH ${API}/3`]: () => json(saved),
    });

    const cuts = await screen.findByRole("slider", { name: "Cuts" });
    expect(cuts).toHaveValue("30");
    expect(
      screen.getByText(/Range 18\/min to 42\/min · from 2 references/),
    ).toBeInTheDocument();
    expect(screen.getByText("Music tempo: no target")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Export JSON" })).toHaveAttribute(
      "href",
      `${API}/3/export`,
    );
    const save = screen.getByRole("button", { name: "Save recipe" });
    expect(save).toBeDisabled();

    fireEvent.change(cuts, { target: { value: "60" } });
    await user.click(
      screen.getByRole("button", { name: "Set a Music tempo target" }),
    );
    const name = within(
      screen.getByRole("region", { name: "Recipe Night phonk" }),
    ).getByLabelText("Name");
    await user.clear(name);
    await user.type(name, "Faster phonk");
    await user.click(save);

    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", `${API}/3`)).toHaveLength(1),
    );
    expect(bodyOf(fetchMock, "PATCH", `${API}/3`)).toEqual({
      name: "Faster phonk",
      description: "Fast cuts on the beat.",
      targets: {
        metrics: {
          cuts_per_minute: { median: 60, low: 48, high: 72, count: 2 },
          mean_luma: DETAIL.targets.metrics.mean_luma,
          bpm: { median: 130, low: 122, high: 138, count: 0 },
        },
        caption_color: "#ffd000",
      },
    });
    expect(
      await screen.findByRole("region", { name: "Recipe Faster phonk" }),
    ).toBeInTheDocument();
  });

  it("creates a recipe only with the rights confirmed", async () => {
    const user = userEvent.setup();
    const created: StyleRecipeDetail = {
      ...DETAIL,
      recipe: { ...RECIPE, id: 4, name: "Calm" },
    };
    const fetchMock = open("/proedit/style-recipes", {
      [`POST ${API}`]: () => json(created, 201),
      [`GET ${API}/4`]: () => json(created),
    });

    expect(await screen.findByText("Pick a style recipe")).toBeInTheDocument();
    const form = screen.getByRole("form", { name: "New style recipe" });
    await user.type(within(form).getByLabelText("Name"), "Calm");
    await user.type(
      within(form).getByLabelText(/Reference links/),
      "https://youtu.be/a\n\nhttps://youtu.be/b",
    );
    const submit = within(form).getByRole("button", { name: "Create recipe" });
    expect(submit).toBeDisabled();
    expect(form).toHaveTextContent(TERMS.notice);
    await user.click(within(form).getByRole("checkbox"));
    await user.click(submit);

    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", API)).toHaveLength(1),
    );
    expect(bodyOf(fetchMock, "POST", API)).toEqual({
      name: "Calm",
      urls: ["https://youtu.be/a", "https://youtu.be/b"],
      rights_confirmed: true,
    });
    expect(
      await screen.findByRole("region", { name: "Recipe Calm" }),
    ).toBeInTheDocument();
  });

  it("analyzes a recipe's references", async () => {
    const user = userEvent.setup();
    const waiting: StyleRecipeDetail = {
      ...DETAIL,
      references: DETAIL.references.map((result) => ({
        ...result,
        reference: { ...result.reference, analyzed_at: null },
      })),
      targets: { metrics: {}, caption_color: null },
    };
    const fetchMock = open("/proedit/style-recipes?recipe=3", {
      [`GET ${API}/3`]: () => json(waiting),
      [`POST ${API}/3/analyze`]: () => json(DETAIL),
    });

    expect(await screen.findAllByText("Not analyzed yet")).toHaveLength(2);
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Analyze references" }),
    );

    expect(await screen.findByRole("slider", { name: "Cuts" })).toHaveValue(
      "30",
    );
    expect(callsTo(fetchMock, "POST", `${API}/3/analyze`)).toHaveLength(1);
    expect(screen.getAllByText("Analyzed (media deleted)")).toHaveLength(2);
  });

  it("imports a recipe file", async () => {
    const user = userEvent.setup({ applyAccept: false });
    const file: StyleRecipeExport = {
      format: "clipforge.style_recipe",
      version: 1,
      name: "Imported",
      description: "",
      reference_count: 2,
      targets: DETAIL.targets,
    };
    const imported = {
      ...DETAIL,
      recipe: { ...RECIPE, id: 5, name: "Imported" },
      references: [],
    };
    const fetchMock = open("/proedit/style-recipes", {
      [`POST ${API}/import`]: () => json(imported, 201),
      [`GET ${API}/5`]: () => json(imported),
    });

    await user.upload(
      await screen.findByLabelText("Recipe file"),
      new File([JSON.stringify(file)], "imported.style-recipe.json", {
        type: "application/json",
      }),
    );

    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", `${API}/import`)).toHaveLength(1),
    );
    expect(bodyOf(fetchMock, "POST", `${API}/import`)).toEqual(file);
    expect(
      await screen.findByText(/this recipe has no reference links/),
    ).toBeInTheDocument();
  });

  it("goes Home while Pro Edit is off", async () => {
    const fetchMock = open("/proedit/style-recipes", {
      "GET /api/proedit/status": () =>
        json({ error: "proedit_disabled", message: "off" }, 404),
    });

    await waitFor(() =>
      expect(callsTo(fetchMock, "GET", "/api/proedit/status")).toHaveLength(1),
    );
    expect(
      await screen.findByRole("link", { name: "Home", current: "page" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Style recipes" })).toBeNull();
    expect(callsTo(fetchMock, "GET", API)).toHaveLength(0);
  });
});
