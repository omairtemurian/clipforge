import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CaptionsOnlyNote } from "./CaptionsOnlyNote";

describe("CaptionsOnlyNote", () => {
  it("says there is no clipping, without a warning up to 3 min", () => {
    render(<CaptionsOnlyNote length={180} onUseAi={() => {}} />);

    expect(screen.getByText(/No clipping: the whole video/)).toBeVisible();
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("warns about a 20 min clip and offers AI clipping", async () => {
    const onUseAi = vi.fn();
    render(<CaptionsOnlyNote length={1200} onUseAi={onUseAi} />);

    expect(
      screen.getByRole("note", { name: "Long captions-only clip" }),
    ).toHaveTextContent("This makes one 20:00 clip, not shorts. Are you sure?");
    await userEvent.click(
      screen.getByRole("button", { name: "Switch to AI clipping" }),
    );
    expect(onUseAi).toHaveBeenCalledOnce();
  });

  it("shows no warning while the length is unknown", () => {
    render(<CaptionsOnlyNote length={null} onUseAi={() => {}} />);

    expect(screen.queryByRole("note")).toBeNull();
  });
});
