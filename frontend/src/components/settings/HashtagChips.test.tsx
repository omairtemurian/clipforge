import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { HashtagChips } from "./HashtagChips";

function Harness({
  start = [],
  onChange,
}: {
  start?: string[];
  onChange?: (tags: string[]) => void;
}) {
  const [tags, setTags] = useState(start);
  return (
    <HashtagChips
      label="Always include"
      value={tags}
      onChange={(next) => {
        setTags(next);
        onChange?.(next);
      }}
    />
  );
}

describe("HashtagChips", () => {
  it("shows the hashtags as chips with a remove button", async () => {
    const onChange = vi.fn();
    render(<Harness start={["pizza", "funny"]} onChange={onChange} />);
    expect(screen.getByText("#pizza")).toBeVisible();

    await userEvent.click(
      screen.getByRole("button", { name: "Remove #pizza" }),
    );
    expect(screen.queryByText("#pizza")).not.toBeInTheDocument();
    expect(onChange).toHaveBeenLastCalledWith(["funny"]);
  });

  it("adds what is typed on Enter, comma or leaving the box", async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const box = screen.getByLabelText("Always include");

    await userEvent.type(box, "#Pizza{Enter}");
    await userEvent.type(box, "funny,");
    await userEvent.type(box, "pizza{Enter}");
    await userEvent.type(box, "last");
    await userEvent.tab();

    expect(onChange).toHaveBeenLastCalledWith(["Pizza", "funny", "last"]);
    expect(screen.getByText("#last")).toBeVisible();
    expect(box).toHaveValue("");
  });

  it("removes the last chip on Backspace in the empty box", async () => {
    const onChange = vi.fn();
    render(<Harness start={["a", "b"]} onChange={onChange} />);
    await userEvent.type(
      screen.getByLabelText("Always include"),
      "{Backspace}",
    );
    expect(onChange).toHaveBeenLastCalledWith(["a"]);
  });
});
