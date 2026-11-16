import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CaptionTemplate } from "@/api/types";
import { mockLayoutAndMedia, renderEditor } from "@/testing/editor";
import { json, styledTemplate } from "@/testing/mockApi";

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

function renderPanels() {
  return renderEditor(undefined, undefined, {
    "GET /api/caption-templates": () =>
      json([
        styledTemplate("karaoke_bold", KARAOKE),
        styledTemplate("minimal", {
          ...KARAOKE,
          size: 40,
          uppercase: false,
          position: "bottom",
        }),
      ]),
  });
}

async function openPanel(
  user: ReturnType<typeof userEvent.setup>,
  name: string,
) {
  await user.click(await screen.findByRole("button", { name }));
  return screen.getByRole("complementary", { name: `${name} panel` });
}

describe("captions panel", () => {
  it("shows the template's style and changes it, one undo step each", async () => {
    const user = userEvent.setup();
    renderPanels();
    const panel = await openPanel(user, "Captions");

    expect(await within(panel).findByText("62 px")).toBeVisible();
    expect(
      within(
        within(panel).getByRole("radiogroup", { name: "Caption position" }),
      )
        .getAllByRole("radio")
        .map((chip) => chip.textContent),
    ).toEqual(["Top", "Middle", "Lower third", "Bottom"]);
    expect(
      within(panel).getByRole("radio", { name: "Lower third" }),
    ).toBeChecked();
    const uppercase = within(panel).getByRole("switch", { name: "Uppercase" });
    expect(uppercase).toBeChecked();
    expect(within(panel).getByLabelText("Caption sample")).toBeVisible();

    await user.click(uppercase);
    await user.click(within(panel).getByRole("switch", { name: "Emoji" }));
    await user.click(within(panel).getByRole("radio", { name: "Bottom" }));

    expect(uppercase).not.toBeChecked();
    expect(within(panel).getByRole("switch", { name: "Emoji" })).toBeChecked();
    expect(within(panel).getByRole("radio", { name: "Bottom" })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(
      within(panel).getByRole("radio", { name: "Lower third" }),
    ).toBeChecked();
    await user.click(
      within(panel).getByRole("button", { name: "Reset to the template" }),
    );
    expect(uppercase).toBeChecked();
    expect(
      within(panel).getByRole("switch", { name: "Emoji" }),
    ).not.toBeChecked();
  });

  it("changes the size with the slider and the colors with the pickers", async () => {
    const user = userEvent.setup();
    renderPanels();
    const panel = await openPanel(user, "Captions");
    await within(panel).findByText("62 px");

    const size = within(panel).getByRole("slider", { name: "Size" });
    size.focus();
    await user.keyboard("{ArrowRight}{ArrowRight}");
    const color = within(panel).getByLabelText("Text");
    fireEvent.pointerDown(color);
    fireEvent.change(color, { target: { value: "#112233" } });
    expect(within(panel).getByText("66 px")).toBeVisible();
    const textField = color.closest("label")!;
    expect(within(textField).getByText("#112233")).toBeVisible();
    // The keyboard steps of the size slider are one gesture: one undo.
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(within(textField).getByText("#FFFFFF")).toBeVisible();
    expect(within(panel).getByText("66 px")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(within(panel).getByText("62 px")).toBeVisible();
  });

  it("drops the style when another template is chosen", async () => {
    const user = userEvent.setup();
    renderPanels();
    const panel = await openPanel(user, "Captions");
    await user.click(
      await within(panel).findByRole("switch", { name: "Emoji" }),
    );

    await user.click(within(panel).getByRole("radio", { name: "Minimal" }));

    expect(await within(panel).findByText("40 px")).toBeVisible();
    expect(
      within(panel).getByRole("switch", { name: "Emoji" }),
    ).not.toBeChecked();
    expect(
      within(panel).getByRole("switch", { name: "Uppercase" }),
    ).not.toBeChecked();
  });

  it("edits the text of a caption word and can undo it", async () => {
    const user = userEvent.setup();
    renderPanels();
    const panel = await openPanel(user, "Captions");

    const words = await within(panel).findByRole("list", {
      name: "Caption words",
    });
    expect(within(words).getAllByRole("textbox")).toHaveLength(5);
    const pizza = within(words).getByDisplayValue("pizza");
    await user.type(pizza, "!");

    expect(pizza).toHaveValue("pizza!");
    expect(within(words).queryByDisplayValue("skip")).toBe(null);
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(within(words).getByDisplayValue("pizza")).toBeVisible();
  });
});

describe("layout panel", () => {
  it("chooses the layout and labels the timeline segment with it", async () => {
    const user = userEvent.setup();
    renderPanels();
    const panel = await openPanel(user, "Layout");

    expect(within(panel).getByRole("radio", { name: "Auto" })).toBeChecked();
    await user.click(within(panel).getByRole("radio", { name: "Split" }));

    expect(within(panel).getByRole("radio", { name: "Split" })).toBeChecked();
    expect(screen.getAllByText("Split").length).toBeGreaterThan(1);
    expect(
      within(panel).getByRole("slider", { name: "Crop position" }),
    ).toHaveAttribute("data-disabled");
    expect(
      within(panel).getByText("Switch to Auto to move the crop."),
    ).toBeVisible();
  });

  it("nudges the crop with the buttons and the slider", async () => {
    const user = userEvent.setup();
    renderPanels();
    const panel = await openPanel(user, "Layout");

    await user.click(
      within(panel).getByRole("button", { name: "Nudge crop right" }),
    );
    await user.click(
      within(panel).getByRole("button", { name: "Nudge crop right" }),
    );
    expect(within(panel).getByText("+10%")).toBeVisible();
    await user.click(
      within(panel).getByRole("button", { name: "Nudge crop left" }),
    );
    expect(within(panel).getByText("+5%")).toBeVisible();

    const slider = within(panel).getByRole("slider", { name: "Crop position" });
    slider.focus();
    await user.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(within(panel).getByText("+3%")).toBeVisible();
    await user.click(
      within(panel).getByRole("button", { name: "Center on speaker" }),
    );
    expect(within(panel).getByText("0%")).toBeVisible();
  });
});
