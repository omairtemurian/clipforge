import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { scored } from "@/testing/mockApi";
import { ScoreBadge } from "./ScoreBadge";

function badge(overall: number) {
  render(<ScoreBadge clip={scored(1, overall)} />);
  return screen.getByRole("button", { name: /Score/ });
}

describe("ScoreBadge", () => {
  it.each([
    [59, "low", "text-muted-foreground"],
    [60, "medium", "text-warning"],
    [79, "medium", "text-warning"],
    [80, "high", "text-success"],
  ])("colors %i as %s", (overall, tone, color) => {
    const trigger = badge(overall);
    expect(trigger).toHaveTextContent(String(overall));
    expect(trigger).toHaveAttribute("data-tone", tone);
    expect(trigger).toHaveClass(color);
  });

  it("opens the breakdown with the four scores and the reason", async () => {
    badge(85);

    await userEvent.click(screen.getByRole("button", { name: /Score 85/ }));

    const hook = screen.getByRole("meter", { name: "Hook" });
    expect(hook).toHaveAttribute("aria-valuenow", "90");
    for (const [name, value] of [
      ["Flow", "80"],
      ["Value", "70"],
      ["Trend", "60"],
    ]) {
      const meter = screen.getByRole("meter", { name });
      expect(within(meter).getByText(value)).toBeInTheDocument();
    }
    expect(screen.getByText("A clean setup and a big laugh.")).toBeVisible();
  });
});
