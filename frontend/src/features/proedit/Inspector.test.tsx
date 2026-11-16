import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { EdlItem } from "@/api/types";
import { edlItem } from "@/testing/proeditFixtures";
import { Inspector } from "./Inspector";

const PUNCH: EdlItem = {
  ...edlItem(1, "zoom_punch", 2, 2.5),
  params: { scale: 1.2, ease: "ease_in_out", ease_frames: 0, center: "face" },
};

describe("Inspector", () => {
  it("asks for an item while none is selected", () => {
    render(<Inspector item={undefined} disabled={false} onApply={vi.fn()} />);

    expect(screen.getByText(/Select an item/)).toBeInTheDocument();
  });

  it("applies the edited params of the item", async () => {
    const user = userEvent.setup();
    const onApply = vi.fn();
    render(<Inspector item={PUNCH} disabled={false} onApply={onApply} />);

    const apply = screen.getByRole("button", { name: "Apply" });
    expect(apply).toBeDisabled();
    await user.clear(screen.getByLabelText("scale"));
    await user.type(screen.getByLabelText("scale"), "1.3");
    await user.selectOptions(screen.getByLabelText("ease"), "back");
    await user.click(apply);

    expect(onApply).toHaveBeenCalledWith({
      ...PUNCH,
      params: { scale: 1.3, ease: "back", ease_frames: 0, center: "face" },
    });
  });

  it("edits a checkbox and text", async () => {
    const user = userEvent.setup();
    const onApply = vi.fn();
    const bed = {
      ...edlItem(2, "music_bed", 0, 5),
      params: { asset: "loop", duck: true },
    };
    render(<Inspector item={bed} disabled={false} onApply={onApply} />);

    await user.click(screen.getByLabelText("duck"));
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(onApply).toHaveBeenCalledWith({
      ...bed,
      params: { asset: "loop", duck: false },
    });
  });

  it("says what is wrong with a number and applies nothing", async () => {
    const user = userEvent.setup();
    const onApply = vi.fn();
    render(<Inspector item={PUNCH} disabled={false} onApply={onApply} />);

    await user.clear(screen.getByLabelText("scale"));
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "scale must be a number",
    );
    expect(onApply).not.toHaveBeenCalled();
  });

  it("is locked while a job runs and says so for an item without params", () => {
    const { rerender } = render(
      <Inspector item={PUNCH} disabled onApply={vi.fn()} />,
    );
    expect(screen.getByLabelText("scale")).toBeDisabled();

    rerender(
      <Inspector
        item={edlItem(3, "freeze_frame", 1, 2)}
        disabled={false}
        onApply={vi.fn()}
      />,
    );
    expect(screen.getByText("This item has no parameters.")).toBeVisible();
  });
});
