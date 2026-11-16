import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CaptionTemplate, Clip } from "@/api/types";
import { CLIP, mockLayoutAndMedia, renderEditor } from "@/testing/editor";
import { callsTo, json, styledTemplate, type Handler } from "@/testing/mockApi";

beforeEach(mockLayoutAndMedia);

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const KARAOKE: CaptionTemplate = {
  font: "Montserrat ExtraBold",
  size: 62,
  primary_color: "#FFFFFF",
  highlight_color: "#FFD23F",
  emphasis_color: "#FF6B35",
  outline: 3.7,
  shadow: 1.9,
  box: false,
  uppercase: true,
  position: "lower_third",
  max_words_per_line: 3,
  outline_color: "#000000",
  max_lines: 1,
  animation: "none",
  emoji: false,
};

const TRANSLATED: Clip = {
  ...CLIP,
  caption_style: {
    ...CLIP.caption_style,
    translation: {
      language: "es",
      cues: [
        { start: 10.2, end: 11.2, text: "Hola pizza", speaker: "S0" },
        { start: 11.3, end: 12, text: "es genial", speaker: "S0" },
      ],
    },
  },
};

/** The editor of CLIP with the caption APIs; PATCH echoes the change. */
function renderCaptions(routes: Record<string, Handler> = {}) {
  return renderEditor(undefined, undefined, {
    "GET /api/caption-templates": () =>
      json([
        styledTemplate("karaoke_bold", KARAOKE),
        styledTemplate("minimal", { ...KARAOKE, size: 40 }),
      ]),
    "GET /api/brand-fonts": () => json(["Montserrat ExtraBold", "Inter"]),
    "GET /api/speech-languages": () =>
      json([
        { code: "es", name: "Spanish" },
        { code: "fr", name: "French" },
      ]),
    "PATCH /api/clips/7": (_url, init) =>
      json({ ...CLIP, ...JSON.parse(String(init?.body)) } satisfies Clip),
    ...routes,
  });
}

async function openCaptions(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Captions" }));
  const panel = screen.getByRole("complementary", { name: "Captions panel" });
  await within(panel).findByText("62 px");
  return panel;
}

/** The body of the only call of method to url. */
async function bodyOf(
  fetchMock: ReturnType<typeof renderCaptions>,
  method: string,
  url: string,
) {
  await waitFor(() => expect(callsTo(fetchMock, method, url)).toHaveLength(1));
  return JSON.parse(String(callsTo(fetchMock, method, url)[0][1]?.body));
}

describe("captions v2", () => {
  it("marks a word with an emoji, a highlight and a color", async () => {
    const user = userEvent.setup();
    const fetchMock = renderCaptions();
    await openCaptions(user);

    await user.click(
      screen.getByRole("button", { name: "Edit word at 00:10.70" }),
    );
    const popover = await screen.findByRole("dialog", { name: 'Word "pizza"' });
    await user.click(within(popover).getByRole("button", { name: "🔥" }));
    await user.click(within(popover).getByRole("radio", { name: "Highlight" }));
    const color = within(popover).getByLabelText("Word color");
    fireEvent.pointerDown(color);
    fireEvent.change(color, { target: { value: "#112233" } });
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    const body = await bodyOf(fetchMock, "PATCH", "/api/clips/7");
    expect(body.caption_style.word_marks).toEqual([
      {
        start: 10.7,
        emphasis: true,
        emoji: "🔥",
        censor: null,
        color: "#112233",
        source: "user",
      },
    ]);
  });

  it("chooses a template in the gallery", async () => {
    const user = userEvent.setup();
    renderCaptions();
    const panel = await openCaptions(user);

    await user.click(
      within(panel).getByRole("button", { name: "All templates" }),
    );
    const gallery = await screen.findByRole("dialog", {
      name: "Caption templates",
    });
    await user.click(within(gallery).getByRole("radio", { name: "Minimal" }));

    expect(screen.queryByRole("dialog", { name: "Caption templates" })).toBe(
      null,
    );
    expect(await within(panel).findByText("40 px")).toBeVisible();
  });

  it("translates the captions and shows the original again", async () => {
    const user = userEvent.setup();
    const fetchMock = renderCaptions({
      "POST /api/clips/7/caption-translation": () => json(TRANSLATED),
      "DELETE /api/clips/7/caption-translation": () => json(CLIP),
    });
    const panel = await openCaptions(user);
    await user.click(within(panel).getByRole("button", { name: "Translate" }));

    await user.selectOptions(
      await within(panel).findByRole("combobox", {
        name: "Translation language",
      }),
      "fr",
    );
    await user.click(
      within(panel).getAllByRole("button", { name: "Translate" })[1],
    );

    expect(
      await bodyOf(fetchMock, "POST", "/api/clips/7/caption-translation"),
    ).toEqual({ language: "fr" });
    expect(
      await within(panel).findByText("Captions in Spanish · 2 lines"),
    ).toBeVisible();
    await user.click(
      within(panel).getByRole("button", { name: "Show the original" }),
    );
    await waitFor(() =>
      expect(within(panel).queryByText(/Captions in Spanish/)).toBe(null),
    );
    expect(
      callsTo(fetchMock, "DELETE", "/api/clips/7/caption-translation"),
    ).toHaveLength(1);
  });

  it("censors automatically and edits the censor list", async () => {
    const user = userEvent.setup();
    const fetchMock = renderCaptions({
      "GET /api/censor-words": () => json({ words: ["darn"] }),
      "PUT /api/censor-words": (_url, init) =>
        json(JSON.parse(String(init?.body))),
    });
    const panel = await openCaptions(user);
    await user.click(within(panel).getByRole("button", { name: "Censor" }));

    await user.click(
      within(panel).getByRole("switch", { name: "Auto censor" }),
    );
    await user.click(within(panel).getByRole("radio", { name: "Mute" }));
    await user.click(
      within(panel).getByRole("button", { name: "Censor list" }),
    );
    const list = await screen.findByRole("textbox", { name: "Censored words" });
    await waitFor(() => expect(list).toHaveValue("darn"));
    await user.type(list, "{Enter}heck");
    await user.click(screen.getByRole("button", { name: "Save list" }));

    expect(await bodyOf(fetchMock, "PUT", "/api/censor-words")).toEqual({
      words: ["darn", "heck"],
    });
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    const body = await bodyOf(fetchMock, "PATCH", "/api/clips/7");
    expect(body.caption_style.censor).toEqual({ auto: true, mode: "mute" });
  });

  it("saves the brand vocabulary and replaces a word everywhere", async () => {
    const user = userEvent.setup();
    const fetchMock = renderCaptions({
      "GET /api/vocabulary": () =>
        json({
          terms: ["ClipForge"],
          corrections: { "clip forge": "ClipForge" },
        }),
      "PUT /api/vocabulary": (_url, init) =>
        json(JSON.parse(String(init?.body))),
      "POST /api/projects/1/replace-everywhere": () =>
        json({ transcript_matches: 3, clips_changed: 2 }),
    });
    const panel = await openCaptions(user);
    await user.click(within(panel).getByRole("button", { name: "Vocabulary" }));
    await user.click(
      within(panel).getByRole("button", { name: "Brand vocabulary" }),
    );

    const dialog = await screen.findByRole("dialog", {
      name: "Brand vocabulary",
    });
    const terms = await within(dialog).findByLabelText("Terms");
    expect(terms).toHaveValue("ClipForge");
    await user.type(terms, "{Enter}Hermes");
    await user.click(
      within(dialog).getByRole("button", { name: "Save vocabulary" }),
    );
    expect(await bodyOf(fetchMock, "PUT", "/api/vocabulary")).toEqual({
      terms: ["ClipForge", "Hermes"],
      corrections: { "clip forge": "ClipForge" },
    });

    await user.type(within(dialog).getByLabelText("Find"), "pizza");
    await user.type(within(dialog).getByLabelText("Replace with"), "pasta");
    await user.click(
      within(dialog).getByRole("button", { name: "Replace everywhere" }),
    );
    expect(
      await bodyOf(fetchMock, "POST", "/api/projects/1/replace-everywhere"),
    ).toEqual({ find: "pizza", replace: "pasta", remember: true });
  });

  it("blocks replace everywhere while the clip has unsaved changes", async () => {
    const user = userEvent.setup();
    renderCaptions({
      "GET /api/vocabulary": () => json({ terms: [], corrections: {} }),
    });
    const panel = await openCaptions(user);
    await user.click(within(panel).getByRole("switch", { name: "Uppercase" }));
    await user.click(within(panel).getByRole("button", { name: "Vocabulary" }));
    await user.click(
      within(panel).getByRole("button", { name: "Brand vocabulary" }),
    );

    const dialog = await screen.findByRole("dialog", {
      name: "Brand vocabulary",
    });
    expect(
      within(dialog).getByText("Save the clip's changes first."),
    ).toBeVisible();
    expect(
      within(dialog).getByRole("button", { name: "Replace everywhere" }),
    ).toBeDisabled();
  });

  it("offers the clip's and the video's transcript downloads", async () => {
    const user = userEvent.setup();
    renderCaptions();
    await user.click(
      await screen.findByRole("button", { name: "Download transcript" }),
    );

    const items = await screen.findAllByRole("menuitem");
    expect(items.map((item) => item.getAttribute("href"))).toEqual([
      "/api/clips/7/transcript.txt",
      "/api/clips/7/transcript.srt",
      "/api/clips/7/transcript.vtt",
      "/api/projects/1/transcript.txt",
      "/api/projects/1/transcript.srt",
      "/api/projects/1/transcript.vtt",
    ]);
  });
});
