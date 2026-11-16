import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Panel, PanelGroup } from "./panel";

describe("Panel", () => {
  it("shows its title as a heading with its actions", () => {
    render(
      <Panel title="Captions" actions={<button>Reset</button>}>
        <p>Body</p>
      </Panel>,
    );
    expect(
      screen.getByRole("heading", { name: "Captions", level: 2 }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Reset" })).toBeVisible();
    expect(screen.getByText("Body")).toBeVisible();
  });

  it("titles a fixed group without a toggle", () => {
    render(
      <PanelGroup title="Words">
        <p>Word list</p>
      </PanelGroup>,
    );
    expect(screen.getByRole("heading", { name: "Words" })).toBeVisible();
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByRole("region", { name: "Words" })).toBeVisible();
  });

  it("folds a collapsible group by click and keyboard", async () => {
    const user = userEvent.setup();
    render(
      <PanelGroup title="Style" collapsible>
        <input aria-label="Size" defaultValue="80" />
      </PanelGroup>,
    );
    const toggle = screen.getByRole("button", { name: "Style" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByLabelText("Size")).toBeVisible();

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByLabelText("Size")).not.toBeVisible();

    toggle.focus();
    await user.keyboard("{Enter}");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    await user.keyboard(" ");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    const body = document.getElementById(
      toggle.getAttribute("aria-controls") ?? "",
    );
    expect(body).not.toBeNull();
    expect(body).not.toBeVisible();
  });

  it("starts closed when asked and keeps typed values when folded", async () => {
    const user = userEvent.setup();
    render(
      <PanelGroup title="Advanced" collapsible defaultOpen={false}>
        <input aria-label="Note" />
      </PanelGroup>,
    );
    const toggle = screen.getByRole("button", { name: "Advanced" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    await user.type(screen.getByLabelText("Note"), "hi");
    await user.click(toggle);
    await user.click(toggle);
    expect(screen.getByLabelText("Note")).toHaveValue("hi");
  });
});
