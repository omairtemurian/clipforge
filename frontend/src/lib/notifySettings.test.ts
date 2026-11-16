import { describe, expect, it } from "vitest";
import { SAVED_SETTINGS } from "@/testing/mockApi";
import {
  notifyDraftOf,
  notifyPatch,
  notifyProblems,
  parsePort,
  isDigestTime,
  parseWarnPercent,
} from "./notifySettings";

describe("notify settings", () => {
  it("sends nothing for an untouched draft", () => {
    expect(notifyPatch(notifyDraftOf(SAVED_SETTINGS), SAVED_SETTINGS)).toEqual(
      {},
    );
  });

  it("sends only what changed, with numbers as numbers", () => {
    const draft = notifyDraftOf(SAVED_SETTINGS);
    draft.text.smtp_host = " mail.example ";
    draft.smtp_port = "465";
    draft.desktop_notifications = true;
    draft.quota_warn_percent = "90";
    draft.digest_time = " 07:30 ";

    expect(notifyPatch(draft, SAVED_SETTINGS)).toEqual({
      digest_time: "07:30",
      smtp_host: "mail.example",
      smtp_port: 465,
      desktop_notifications: true,
      quota_warn_percent: 90,
    });
  });

  it("sends the typed password, or an empty one to remove it", () => {
    const draft = notifyDraftOf(SAVED_SETTINGS);
    draft.smtp_password = { typed: "pw", clear: false };
    expect(notifyPatch(draft, SAVED_SETTINGS)).toEqual({ smtp_password: "pw" });

    draft.smtp_password = { typed: "", clear: true };
    expect(notifyPatch(draft, SAVED_SETTINGS)).toEqual({ smtp_password: "" });
  });

  it("checks the port and the warning percent", () => {
    expect(parsePort("587")).toBe(587);
    expect([parsePort("0"), parsePort("65536"), parsePort("5.5")]).toEqual([
      null,
      null,
      null,
    ]);
    expect(parseWarnPercent("80.5")).toBe(80.5);
    expect([parseWarnPercent(""), parseWarnPercent("100")]).toEqual([
      null,
      null,
    ]);

    const draft = notifyDraftOf(SAVED_SETTINGS);
    draft.smtp_port = "x";
    draft.quota_warn_percent = "0";
    expect(Object.keys(notifyProblems(draft))).toEqual([
      "smtp_port",
      "quota_warn_percent",
    ]);
    expect(notifyPatch(draft, SAVED_SETTINGS)).toEqual({});
  });

  it("checks the digest time and lets it be turned off", () => {
    expect(["08:00", "23:59", "00:00", ""].map(isDigestTime)).toEqual([
      true,
      true,
      true,
      true,
    ]);
    expect(["8:00", "24:00", "07:60", "8am"].map(isDigestTime)).toEqual([
      false,
      false,
      false,
      false,
    ]);

    const draft = notifyDraftOf(SAVED_SETTINGS);
    draft.digest_time = "";
    expect(notifyPatch(draft, SAVED_SETTINGS)).toEqual({ digest_time: "" });
    draft.digest_time = "9";
    expect(Object.keys(notifyProblems(draft))).toEqual(["digest_time"]);
    expect(notifyPatch(draft, SAVED_SETTINGS)).toEqual({});
  });
});
