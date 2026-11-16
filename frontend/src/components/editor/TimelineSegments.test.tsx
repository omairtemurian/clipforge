import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TimelineSegments } from "@/components/editor/TimelineSegments";

const VIEW = { start: 0, end: 100 };
const PARTS: [number, number][] = [
  [0, 2],
  [2, 60],
];

function renderRow(width: number) {
  render(
    <TimelineSegments
      view={VIEW}
      parts={PARTS}
      selected={null}
      labelAt={() => "Auto"}
      width={width}
      onSelect={() => {}}
    />,
  );
}

describe("TimelineSegments labels", () => {
  it("drops the label of a chip too narrow for it, keeping the tooltip", () => {
    renderRow(1000);
    const [short, long] = screen.getAllByRole("button");
    expect(short).toHaveTextContent("");
    expect(short).toHaveAttribute("title", "Auto");
    expect(long).toHaveTextContent("Auto");
  });

  it("shows every label while the row is not measured", () => {
    renderRow(0);
    for (const chip of screen.getAllByRole("button")) {
      expect(chip).toHaveTextContent("Auto");
    }
  });
});
