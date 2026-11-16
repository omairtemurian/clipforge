import { describe, expect, it, vi } from "vitest";
import { approval, draft } from "@/testing/draftFixtures";
import { post } from "@/testing/postFixtures";
import {
  approvalMessage,
  freshnessLabel,
  handleInboxKey,
  rateLabel,
  REJECT_REASONS,
  stepIndex,
  type InboxKeyHandlers,
} from "./drafts";

function handlers(): InboxKeyHandlers {
  return {
    approve: vi.fn(),
    reject: vi.fn(),
    edit: vi.fn(),
    move: vi.fn(),
    cancel: vi.fn(),
  };
}

function press(key: string, init: KeyboardEventInit = {}, target?: Element) {
  const event = new KeyboardEvent("keydown", {
    key,
    cancelable: true,
    ...init,
  });
  if (target) Object.defineProperty(event, "target", { value: target });
  return event;
}

describe("REJECT_REASONS", () => {
  it("offers the six reasons of the spec in order", () => {
    expect(REJECT_REASONS.map((r) => r.label)).toEqual([
      "Boring",
      "Out of context",
      "Bad crop",
      "Bad captions",
      "Too long",
      "Other",
    ]);
  });
});

describe("rateLabel", () => {
  it("shows the rate per 1,000 views, or that none is set", () => {
    expect(rateLabel({ rate_per_1k_usd: 0.5 })).toBe("$0.50 per 1,000 views");
    expect(rateLabel({ rate_per_1k_usd: null })).toBe("No rate set");
  });
});

describe("freshnessLabel", () => {
  const now = new Date("2026-11-02T12:00:00Z");

  it("says how long ago the source was uploaded", () => {
    expect(freshnessLabel("2026-11-02T11:59:40Z", now)).toBe(
      "Uploaded just now",
    );
    expect(freshnessLabel("2026-11-02T11:20:00Z", now)).toBe(
      "Uploaded 40 min ago",
    );
    expect(freshnessLabel("2026-11-02T07:00:00", now)).toBe("Uploaded 5 h ago");
    expect(freshnessLabel("2026-11-01T00:00:00Z", now)).toBe(
      "Uploaded 36 h ago",
    );
    expect(freshnessLabel("2026-10-30T12:00:00Z", now)).toBe(
      "Uploaded 3 days ago",
    );
  });

  it("is null when the upload time is unknown", () => {
    expect(freshnessLabel(null, now)).toBeNull();
    expect(freshnessLabel("not a date", now)).toBeNull();
  });
});

describe("handleInboxKey", () => {
  it.each([
    ["a", "approve"],
    ["A", "approve"],
    ["r", "reject"],
    ["e", "edit"],
    ["Escape", "cancel"],
  ] as const)("%s calls %s", (key, name) => {
    const calls = handlers();
    const event = press(key);
    handleInboxKey(event, calls);
    expect(calls[name]).toHaveBeenCalledOnce();
    expect(event.defaultPrevented).toBe(true);
  });

  it("J and K select the next and the previous draft", () => {
    const calls = handlers();
    handleInboxKey(press("j"), calls);
    handleInboxKey(press("k"), calls);
    expect(vi.mocked(calls.move).mock.calls).toEqual([[1], [-1]]);
  });

  it("ignores typing, modifier keys and other keys", () => {
    const calls = handlers();
    const input = document.createElement("input");
    handleInboxKey(press("a", {}, input), calls);
    handleInboxKey(press("a", { metaKey: true }), calls);
    handleInboxKey(press("r", { ctrlKey: true }), calls);
    handleInboxKey(press("e", { altKey: true }), calls);
    const other = press("x");
    handleInboxKey(other, calls);
    expect(
      Object.values(calls).every((fn) => !vi.mocked(fn).mock.calls.length),
    ).toBe(true);
    expect(other.defaultPrevented).toBe(false);
  });
});

describe("stepIndex", () => {
  it("moves inside the list", () => {
    expect(stepIndex(0, 1, 3)).toBe(1);
    expect(stepIndex(2, 1, 3)).toBe(2);
    expect(stepIndex(0, -1, 3)).toBe(0);
    expect(stepIndex(0, 1, 0)).toBe(0);
  });
});

describe("approvalMessage", () => {
  it("names the slot of the first post", () => {
    const one = approval(draft());
    expect(approvalMessage(one)).toMatch(/^Approved: 1 post scheduled for /);
    const two = {
      ...one,
      posts: [
        post({ id: 2, scheduled_at: "2030-01-15T08:00:00Z" }),
        post({ id: 1, scheduled_at: "2030-01-14T08:00:00Z" }),
      ],
    };
    const text = approvalMessage(two);
    expect(text).toMatch(/^Approved: 2 posts scheduled, the first for /);
    expect(text).toContain("2030");
    expect(text).toContain("14");
  });

  it("says queued when no post has a time", () => {
    const one = approval(draft());
    one.posts[0].scheduled_at = null;
    expect(approvalMessage(one)).toBe("Approved: 1 post queued");
  });
});
