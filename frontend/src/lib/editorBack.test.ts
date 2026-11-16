import { describe, expect, it } from "vitest";
import { backLink } from "./editorBack";

describe("backLink", () => {
  it("goes back to the page that opened the editor", () => {
    expect(
      backLink(
        { backTo: "/inbox", backLabel: "Back to the approval inbox" },
        4,
      ),
    ).toEqual({ to: "/inbox", label: "Back to the approval inbox" });
  });

  it("goes back to the project's clips otherwise", () => {
    const clips = { to: "/projects/4", label: "Back to clips" };
    expect(backLink(null, 4)).toEqual(clips);
    expect(backLink({ backTo: 3 }, 4)).toEqual(clips);
  });
});
