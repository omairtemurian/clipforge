import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Clip, HookTemplateInfo, TrackItem } from "@/api/types";
import {
  CLIP,
  mockLayoutAndMedia,
  renderEditor,
  WORDS,
} from "@/testing/editor";
import { callsTo, clip, json, timelineOf } from "@/testing/mockApi";

beforeEach(mockLayoutAndMedia);

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const TEMPLATES: HookTemplateInfo[] = [
  {
    name: "slam_pop",
    label: "Slam pop",
    description: "Big words slam in with a punch.",
    duration: 2.5,
    punch: 1.2,
    sound: true,
  },
  {
    name: "slow_push",
    label: "Slow push",
    description: "A calm push-in under a line.",
    duration: 3,
    punch: 1.1,
    sound: false,
  },
];

function textItem(id: string, text: string, start: number): TrackItem {
  return {
    id,
    kind: "text",
    asset_id: null,
    start,
    end: start + 2,
    props: { text },
  };
}

const WITH_HOOK = clip({
  ...CLIP,
  hook: { template: "slam_pop", text: "Wait for it", duration: 2.5 },
});

const WITH_GRAPHICS = clip({
  ...CLIP,
  tracks: {
    ...timelineOf(10, 40),
    text: [
      textItem("headline", "He ate it all", 0),
      textItem("mg-1", "Maria Lopez\nChef", 3),
      textItem("mg-2", "1,200", 8),
    ],
  },
});

/** The body of the one call to method and url. */
function bodyOf(
  fetchMock: ReturnType<typeof renderEditor>,
  method: string,
  url: string,
) {
  const calls = callsTo(fetchMock, method, url);
  expect(calls).toHaveLength(1);
  const body = calls[0][1]?.body;
  return body === undefined ? undefined : JSON.parse(String(body));
}

async function openPanel(
  name: string,
  data: Clip,
  routes: Parameters<typeof renderEditor>[2] = {},
) {
  const user = userEvent.setup();
  const fetchMock = renderEditor(data, WORDS, {
    "GET /api/hook-templates": () => json(TEMPLATES),
    ...routes,
  });
  await screen.findByRole("heading", { name: "Pizza night" });
  await user.click(screen.getByRole("button", { name }));
  return { user, fetchMock };
}

describe("hooks panel", () => {
  it("adds a hook from the chosen template and the captions", async () => {
    const answer = {
      ...CLIP,
      hook: {
        template: "slow_push",
        text: "Hello pizza is great",
        duration: 2.5,
      },
    };
    const { user, fetchMock } = await openPanel("Hooks", CLIP, {
      "POST /api/clips/7/hook": () => json(answer),
    });
    await user.click(await screen.findByRole("button", { name: /Slow push/ }));
    await user.click(screen.getByRole("button", { name: "Add hook" }));

    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", "/api/clips/7/hook")).toHaveLength(1),
    );
    expect(bodyOf(fetchMock, "POST", "/api/clips/7/hook")).toEqual({
      template: "slow_push",
      source: "captions",
      text: null,
      duration: 3,
    });
    expect(await screen.findByLabelText("Hook text")).toHaveValue(
      "Hello pizza is great",
    );
    expect(screen.getByRole("button", { name: /Slow push/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("adds a hook with the user's own text", async () => {
    const { user, fetchMock } = await openPanel("Hooks", CLIP, {
      "POST /api/clips/7/hook": () => json(WITH_HOOK),
    });
    await screen.findByRole("button", { name: /Slam pop/ });
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Hook text from" }),
      "text",
    );
    const add = screen.getByRole("button", { name: "Add hook" });
    expect(add).toBeDisabled();
    await user.type(screen.getByLabelText("Your hook text"), "Wait for it");
    await user.click(add);

    await waitFor(() =>
      expect(callsTo(fetchMock, "POST", "/api/clips/7/hook")).toHaveLength(1),
    );
    expect(bodyOf(fetchMock, "POST", "/api/clips/7/hook")).toMatchObject({
      template: "slam_pop",
      source: "text",
      text: "Wait for it",
    });
    expect(await screen.findByLabelText("Hook text")).toHaveValue(
      "Wait for it",
    );
  });

  it("changes the template, the text and the length of the hook", async () => {
    let current = WITH_HOOK;
    const { user, fetchMock } = await openPanel("Hooks", WITH_HOOK, {
      "PATCH /api/clips/7/hook": (_url, init) => {
        current = clip({
          ...current,
          hook: { ...current.hook!, ...JSON.parse(String(init?.body)) },
        });
        return json(current);
      },
    });
    await user.click(await screen.findByRole("button", { name: /Slow push/ }));
    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/clips/7/hook")).toHaveLength(1),
    );
    expect(callsTo(fetchMock, "PATCH", "/api/clips/7/hook")[0][1]?.body).toBe(
      JSON.stringify({ template: "slow_push" }),
    );

    const text = screen.getByLabelText("Hook text");
    await user.clear(text);
    await user.type(text, "Look at this");
    await user.click(screen.getByRole("button", { name: "Save text" }));
    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/clips/7/hook")).toHaveLength(2),
    );
    expect(callsTo(fetchMock, "PATCH", "/api/clips/7/hook")[1][1]?.body).toBe(
      JSON.stringify({ text: "Look at this" }),
    );

    const slider = screen.getByRole("slider", { name: "Hook length" });
    slider.focus();
    await user.keyboard("{ArrowRight}");
    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/clips/7/hook")).toHaveLength(3),
    );
    expect(callsTo(fetchMock, "PATCH", "/api/clips/7/hook")[2][1]?.body).toBe(
      JSON.stringify({ duration: 2.6 }),
    );
  });

  it("writes the hook text again with the AI and removes the hook", async () => {
    const { user, fetchMock } = await openPanel("Hooks", WITH_HOOK, {
      "POST /api/clips/7/hook": () =>
        json(
          clip({
            ...CLIP,
            hook: {
              template: "slam_pop",
              text: "Nobody saw this",
              duration: 2.5,
            },
          }),
        ),
      "DELETE /api/clips/7/hook": () => json(CLIP),
    });
    await user.click(
      await screen.findByRole("button", { name: "Write a new line" }),
    );
    expect(await screen.findByLabelText("Hook text")).toHaveValue(
      "Nobody saw this",
    );
    expect(bodyOf(fetchMock, "POST", "/api/clips/7/hook")).toMatchObject({
      template: "slam_pop",
      source: "theme",
      text: null,
    });

    await user.click(screen.getByRole("button", { name: "Remove hook" }));
    expect(
      await screen.findByRole("button", { name: "Add hook" }),
    ).toBeInTheDocument();
    expect(callsTo(fetchMock, "DELETE", "/api/clips/7/hook")).toHaveLength(1);
  });
});

describe("headline", () => {
  it("regenerates the headline with the AI and keeps the clip it answers", async () => {
    const { user, fetchMock } = await openPanel("Hooks", WITH_GRAPHICS, {
      "POST /api/clips/7/headline": () =>
        json(clip({ ...WITH_GRAPHICS, hook_text: "A whole pizza" })),
    });
    await user.click(
      await screen.findByRole("button", { name: "Write a new headline" }),
    );
    expect(await screen.findByLabelText("Headline text")).toHaveValue(
      "A whole pizza",
    );
    expect(bodyOf(fetchMock, "POST", "/api/clips/7/headline")).toEqual({
      text: null,
    });
  });

  it("sets a typed headline and removes it", async () => {
    const { user, fetchMock } = await openPanel("Hooks", WITH_GRAPHICS, {
      "POST /api/clips/7/headline": () =>
        json(clip({ ...WITH_GRAPHICS, hook_text: "Typed headline" })),
      "DELETE /api/clips/7/headline": () =>
        json(clip({ ...CLIP, hook_text: "" })),
    });
    const input = await screen.findByLabelText("Headline text");
    const set = screen.getByRole("button", { name: "Set headline" });
    expect(set).toBeDisabled();
    await user.clear(input);
    await user.type(input, "Typed headline");
    await user.click(set);
    await waitFor(() =>
      expect(bodyOf(fetchMock, "POST", "/api/clips/7/headline")).toEqual({
        text: "Typed headline",
      }),
    );

    await user.click(
      await screen.findByRole("button", { name: "Remove headline" }),
    );
    await waitFor(() =>
      expect(screen.getByLabelText("Headline text")).toHaveValue(""),
    );
    expect(
      screen.getByRole("button", { name: "Write with AI" }),
    ).toBeInTheDocument();
  });
});

describe("motion graphics panel", () => {
  it("finds graphics with the chosen count and lists them", async () => {
    const { user, fetchMock } = await openPanel("Graphics", CLIP, {
      "POST /api/clips/7/motion-graphics": () => json(WITH_GRAPHICS),
    });
    expect(screen.getByText("No motion graphics")).toBeInTheDocument();
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Most graphics" }),
      "2",
    );
    await user.click(screen.getByRole("button", { name: "Find graphics" }));

    const list = await screen.findByRole("list", { name: "Motion graphics" });
    expect(within(list).getAllByRole("button")).toHaveLength(2);
    expect(within(list).getByText("Maria Lopez · Chef")).toBeInTheDocument();
    expect(within(list).getByText("1,200")).toBeInTheDocument();
    expect(bodyOf(fetchMock, "POST", "/api/clips/7/motion-graphics")).toEqual({
      max_items: 2,
    });
    expect(
      screen.getByRole("button", { name: "Find new graphics" }),
    ).toBeInTheDocument();
  });

  it("edits the text of a graphic and saves it with the tracks", async () => {
    const { user, fetchMock } = await openPanel("Graphics", WITH_GRAPHICS, {
      "PATCH /api/clips/7": () => json(WITH_GRAPHICS),
      "PATCH /api/clips/7/tracks": (_url, init) =>
        json({ ...WITH_GRAPHICS, tracks: JSON.parse(String(init?.body)) }),
    });
    await user.click(
      await within(
        await screen.findByRole("list", { name: "Motion graphics" }),
      ).findByRole("button", { name: /1,200/ }),
    );
    const text = screen.getByLabelText("Text");
    fireEvent.change(text, { target: { value: "1,500" } });
    expect(
      within(screen.getByRole("list", { name: "Motion graphics" })).getByText(
        "1,500",
      ),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/clips/7/tracks")).toHaveLength(
        1,
      ),
    );
    const saved = bodyOf(fetchMock, "PATCH", "/api/clips/7/tracks");
    const items = saved.text as TrackItem[];
    expect(items.map((item) => item.id)).toEqual(["headline", "mg-1", "mg-2"]);
    expect(items[2].props).toMatchObject({ text: "1,500" });
  });

  it("deletes one graphic and removes all of them", async () => {
    const { user, fetchMock } = await openPanel("Graphics", WITH_GRAPHICS, {
      "PATCH /api/clips/7": () => json(WITH_GRAPHICS),
      "PATCH /api/clips/7/tracks": (_url, init) =>
        json({ ...WITH_GRAPHICS, tracks: JSON.parse(String(init?.body)) }),
      "DELETE /api/clips/7/motion-graphics": () =>
        json(
          clip({
            ...WITH_GRAPHICS,
            tracks: {
              ...WITH_GRAPHICS.tracks,
              text: [WITH_GRAPHICS.tracks.text[0]],
            },
          }),
        ),
    });
    await user.click(
      await within(
        await screen.findByRole("list", { name: "Motion graphics" }),
      ).findByRole("button", { name: /Maria Lopez/ }),
    );
    await user.click(screen.getByRole("button", { name: "Delete graphic" }));
    expect(
      within(
        screen.getByRole("list", { name: "Motion graphics" }),
      ).getAllByRole("button"),
    ).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(callsTo(fetchMock, "PATCH", "/api/clips/7/tracks")).toHaveLength(
        1,
      ),
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Remove all" })).toBeEnabled(),
    );
    await user.click(screen.getByRole("button", { name: "Remove all" }));
    expect(await screen.findByText("No motion graphics")).toBeInTheDocument();
    expect(
      callsTo(fetchMock, "DELETE", "/api/clips/7/motion-graphics"),
    ).toHaveLength(1);
  });
});
