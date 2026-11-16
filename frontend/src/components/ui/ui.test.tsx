import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FolderOpenIcon } from "@phosphor-icons/react";
import { describe, expect, it, vi } from "vitest";
import { Card } from "./card";
import { EmptyState } from "./empty-state";
import { NativeSelect } from "./native-select";
import { Pill } from "./pill";
import { Skeleton } from "./skeleton";

describe("ui primitives", () => {
  it.each([
    ["success", "text-success"],
    ["warning", "text-warning"],
    ["danger", "text-destructive"],
    ["overlay", "bg-overlay"],
  ] as const)("colors a %s pill with the token", (tone, token) => {
    render(<Pill tone={tone}>Ready</Pill>);
    const pill = screen.getByText("Ready");
    expect(pill).toHaveAttribute("data-tone", tone);
    expect(pill).toHaveClass(token, "text-caption");
  });

  it("keeps the type scale next to a text color", () => {
    render(
      <Pill tone="primary" className="text-success">
        Live
      </Pill>,
    );
    expect(screen.getByText("Live")).toHaveClass(
      "text-caption",
      "text-success",
    );
    expect(screen.getByText("Live")).not.toHaveClass("text-primary-ink");
  });

  it("shows an empty state with its one action", async () => {
    const onClick = vi.fn();
    render(
      <EmptyState
        icon={FolderOpenIcon}
        title="Nothing here"
        action={<button onClick={onClick}>Start</button>}
      >
        Add something first.
      </EmptyState>,
    );
    expect(screen.getByText("Nothing here")).toBeVisible();
    expect(screen.getByText("Add something first.")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Start" }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("changes a native select", async () => {
    const onChange = vi.fn();
    render(
      <NativeSelect aria-label="Sort" defaultValue="a" onChange={onChange}>
        <option value="a">A</option>
        <option value="b">B</option>
      </NativeSelect>,
    );
    await userEvent.selectOptions(screen.getByLabelText("Sort"), "b");
    expect(onChange).toHaveBeenCalled();
    expect(screen.getByLabelText("Sort")).toHaveValue("b");
  });

  it("hides skeletons from assistive tech and draws cards", () => {
    const { container } = render(
      <>
        <Skeleton className="h-4" />
        <Card interactive>Body</Card>
      </>,
    );
    expect(container.querySelector("[data-slot=skeleton]")).toHaveAttribute(
      "aria-hidden",
    );
    expect(screen.getByText("Body")).toHaveClass("shadow-card", "bg-card");
  });
});
