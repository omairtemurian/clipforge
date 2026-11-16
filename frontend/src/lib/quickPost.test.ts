import { beforeEach, describe, expect, it } from "vitest";
import type { SocialAccount } from "@/api/types";
import {
  defaultAccounts,
  lastPlatforms,
  rememberPlatforms,
  startingIds,
} from "./quickPost";

function account(id: number, overrides: Partial<SocialAccount>): SocialAccount {
  return {
    id,
    platform: "youtube",
    external_id: `e${id}`,
    display_name: `A${id}`,
    token_ref: `r${id}`,
    scopes: [],
    connected_at: "2026-11-01T10:00:00",
    restrictions: [],
    is_default: false,
    avatar_url: null,
    always_hashtags: [],
    ...overrides,
  };
}

const ACCOUNTS = [
  account(1, {}),
  account(2, { is_default: true }),
  account(3, { platform: "tiktok" }),
];

beforeEach(() => localStorage.clear());

describe("quick post defaults", () => {
  it("takes the starred account, else the first, of each platform", () => {
    expect(defaultAccounts(ACCOUNTS).map((a) => a.id)).toEqual([2, 3]);
  });

  it("starts with the last platforms that have an account", () => {
    expect([...startingIds(ACCOUNTS, ["tiktok"])]).toEqual([3]);
    expect([...startingIds(ACCOUNTS, ["instagram"])]).toEqual([2, 3]);
    expect([...startingIds(ACCOUNTS, [])]).toEqual([2, 3]);
  });

  it("remembers the platforms and ignores a damaged value", () => {
    rememberPlatforms(["tiktok", "youtube"]);
    expect(lastPlatforms()).toEqual(["youtube", "tiktok"]);
    localStorage.setItem("clipforge.quickPost.platforms", "{oops");
    expect(lastPlatforms()).toEqual([]);
  });
});
