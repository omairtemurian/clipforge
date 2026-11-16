import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("cn", () => {
  it("keeps a type-scale token next to a text color", () => {
    expect(cn("text-body text-muted-foreground")).toBe(
      "text-body text-muted-foreground",
    );
  });

  it("lets a later size or token win", () => {
    expect(cn("text-sm", "text-caption")).toBe("text-caption");
    expect(cn("text-micro text-muted-foreground", "text-body")).toBe(
      "text-muted-foreground text-body",
    );
    expect(cn("px-page", "px-4")).toBe("px-4");
    expect(cn("max-w-form", "max-w-wide")).toBe("max-w-wide");
    expect(cn("shadow-card", "shadow-popover")).toBe("shadow-popover");
  });
});
