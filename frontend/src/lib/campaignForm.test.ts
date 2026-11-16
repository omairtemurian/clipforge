import { describe, expect, it } from "vitest";
import { campaign } from "@/testing/campaignFixtures";
import {
  campaignBody,
  campaignChanges,
  draftOf,
  pastedLines,
  pastedTags,
  validateCampaign,
} from "./campaignForm";

describe("pasted text", () => {
  it("splits tags on spaces, commas and newlines", () => {
    expect(pastedTags("#a, #b\n@c  #d")).toEqual(["#a", "#b", "@c", "#d"]);
    expect(pastedTags("  ")).toEqual([]);
  });

  it("splits links into trimmed, non-empty lines", () => {
    expect(pastedLines(" https://a.test \r\n\n https://b.test")).toEqual([
      "https://a.test",
      "https://b.test",
    ]);
  });
});

describe("campaign draft", () => {
  it("round-trips a saved campaign into the same body", () => {
    const saved = campaign({
      end_date: "2026-12-31",
      monetization_allowed_elsewhere: false,
    });
    const body = campaignBody(draftOf(saved));

    expect(body.required_hashtags).toEqual(["afro", "clips"]);
    expect(body.monetization_allowed_elsewhere).toBe(false);
    expect(body.end_date).toBe("2026-12-31");
    expect(campaignChanges(draftOf(saved), saved)).toEqual({});
  });

  it("keeps the heavy-edits switch as saved (unknown for a new campaign)", () => {
    const saved = campaign({ allow_heavy_edits: "true" });

    expect(campaignBody(draftOf(saved)).allow_heavy_edits).toBe("true");
    expect(campaignBody(draftOf()).allow_heavy_edits).toBe("unknown");
    expect(campaignChanges(draftOf(saved), saved)).toEqual({});
  });

  it("never patches the heavy-edits switch (the Pro Edit section saves it)", () => {
    const stale = draftOf(campaign({ allow_heavy_edits: "unknown" }));

    expect(
      campaignChanges(stale, campaign({ allow_heavy_edits: "true" })),
    ).toEqual({});
  });

  it("sends only the changed fields (a same permission link keeps its date)", () => {
    const saved = campaign({ permission_source_url: "https://a.test/proof" });
    const draft = { ...draftOf(saved), name: "Renamed", minDuration: "" };

    expect(campaignChanges(draft, saved)).toEqual({
      name: "Renamed",
      min_duration_s: null,
    });
  });

  it("turns blank text into null and numbers into numbers", () => {
    const body = campaignBody({
      ...draftOf(),
      name: " New ",
      rate: "0.75",
      campaignUrl: " ",
    });

    expect(body).toMatchObject({
      name: "New",
      rate_per_1k_usd: 0.75,
      campaign_url: null,
      monetization_allowed_elsewhere: null,
      allowed_platforms: [],
    });
  });
});

describe("validateCampaign", () => {
  it("accepts a named campaign", () => {
    expect(validateCampaign({ ...draftOf(), name: "A" })).toEqual({});
  });

  it("finds each problem of the entries", () => {
    const problems = validateCampaign({
      ...draftOf(),
      name: " ",
      channelUrls: "https://ok.test\nnot a link",
      campaignUrl: "ftp://x.test",
      permissionUrl: "nope",
      rate: "-1",
      minDuration: "50",
      maxDuration: "20",
      screenshot: new File(["x"], "p.gif", { type: "image/gif" }),
    });

    expect(Object.keys(problems).sort()).toEqual([
      "campaignUrl",
      "channelUrls",
      "minDuration",
      "name",
      "permissionUrl",
      "rate",
      "screenshot",
    ]);
  });

  it("rejects a length of 0 or text", () => {
    const problems = validateCampaign({
      ...draftOf(),
      name: "A",
      minDuration: "0",
      maxDuration: "abc",
    });

    expect(problems.minDuration).toBe("The minimum must be over 0.");
    expect(problems.maxDuration).toBe("The maximum must be over 0.");
  });
});
