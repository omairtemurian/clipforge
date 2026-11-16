import { describe, expect, it } from "vitest";
import type { ApiKey } from "@/api/types";
import { lastUsedLabel, recentlyUsed } from "./apiKeys";

const NOW = new Date("2026-11-02T12:00:00Z");

function key(id: number, last_used_at: string | null): ApiKey {
  return {
    id,
    name: `key ${id}`,
    prefix: "cfk_AbCdEf",
    created_at: "2026-10-01T00:00:00Z",
    last_used_at,
  };
}

describe("API key activity", () => {
  it("lists the keys used in the last 7 days, latest first", () => {
    const keys = [
      key(1, "2026-11-01T12:00:00Z"),
      key(2, null),
      key(3, "2026-10-20T12:00:00Z"),
      key(4, "2026-11-02T11:55:00Z"),
    ];
    expect(recentlyUsed(keys, NOW).map(({ id }) => id)).toEqual([4, 1]);
  });

  it("says when a key was last used", () => {
    expect(lastUsedLabel(key(1, null), NOW)).toBe("Never used");
    expect(lastUsedLabel(key(1, "2026-11-02T11:55:00Z"), NOW)).toBe(
      "Last used 5 min ago",
    );
  });
});
