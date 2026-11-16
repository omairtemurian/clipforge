import { describe, expect, it } from "vitest";
import { post, socialAccount } from "@/testing/postFixtures";
import {
  blankDrafts,
  blankFields,
  bulkProblem,
  bulkTargets,
  bulkText,
  postCountLabel,
} from "./bulkSchedule";
import {
  editFieldsOf,
  editedText,
  fieldsChanged,
  isEditable,
  isPostPlatform,
  textOf,
} from "./postEdit";

const CLIP = {
  title: "Pizza night",
  description: "A whole pizza.",
  hashtags: ["pizza"],
};

const NO_TEXT = {
  title: null,
  caption: null,
  hashtags: null,
  link: null,
  privacy: null,
  collaborators: [],
  options: {},
};

describe("post details form", () => {
  it("fills a post that took the clip's texts from the clip", () => {
    const fields = editFieldsOf("youtube", NO_TEXT, CLIP);

    expect(fields).toEqual({
      title: "Pizza night",
      caption: "A whole pizza.",
      hashtags: "#pizza",
      privacy: "public",
    });
    expect(editFieldsOf("tiktok", NO_TEXT, CLIP)).toEqual({
      title: "",
      caption: "Pizza night\n\nA whole pizza.",
      hashtags: "#pizza",
      privacy: "",
    });
  });

  it("keeps the post's own text and the fields the user left alone", () => {
    const own = { ...NO_TEXT, caption: "Hungry?", privacy: "SELF_ONLY" };
    const initial = editFieldsOf("tiktok", { ...own, title: "" }, CLIP);
    expect(initial.caption).toBe("Hungry?");

    const text = editedText("tiktok", own, initial, {
      ...initial,
      caption: "Very hungry?",
    });

    expect(text).toEqual({ ...own, title: "", caption: "Very hungry?" });
    expect(text.hashtags).toBeNull();
    expect(
      editedText("youtube", NO_TEXT, editFieldsOf("youtube", NO_TEXT, CLIP), {
        ...editFieldsOf("youtube", NO_TEXT, CLIP),
        hashtags: "#food #night",
      }).hashtags,
    ).toEqual(["food", "night"]);
    expect(
      fieldsChanged(initial, { ...initial, privacy: "PUBLIC_TO_EVERYONE" }),
    ).toBe(true);
    expect(fieldsChanged(initial, { ...initial })).toBe(false);
  });

  it("reads the payload's text and which posts may change", () => {
    expect(textOf(post({ payload: { text: { caption: "Hi" } } })).caption).toBe(
      "Hi",
    );
    expect(textOf(post()).title).toBeNull();
    expect(isEditable(post({ status: "queued" }))).toBe(true);
    expect(isEditable(post({ status: "published" }))).toBe(false);
    expect(isPostPlatform("youtube")).toBe(true);
    expect(isPostPlatform("x")).toBe(false);
  });
});

describe("bulk scheduler form", () => {
  it("leaves blank fields to each clip", () => {
    expect(bulkText("youtube", blankFields("youtube"))).toEqual({
      ...NO_TEXT,
      privacy: "public",
    });
    expect(
      bulkText("tiktok", {
        title: "ignored",
        caption: "Same caption",
        hashtags: "#a b",
        privacy: "SELF_ONLY",
      }),
    ).toEqual({
      ...NO_TEXT,
      caption: "Same caption",
      hashtags: ["a", "b"],
      privacy: "SELF_ONLY",
    });
  });

  it("makes a target per account with its platform's text", () => {
    const drafts = blankDrafts();
    drafts.tiktok.privacy = "PUBLIC_TO_EVERYONE";
    const accounts = [
      socialAccount({ id: 1 }),
      socialAccount({ id: 2, platform: "tiktok" }),
      socialAccount({ id: 3, platform: "x" }),
    ];

    expect(bulkTargets(accounts, drafts)).toEqual([
      { account_id: 1, text: { ...NO_TEXT, privacy: "public" } },
      { account_id: 2, text: { ...NO_TEXT, privacy: "PUBLIC_TO_EVERYONE" } },
    ]);
  });

  it("says what is missing and counts the posts", () => {
    const tiktok = [socialAccount({ id: 2, platform: "tiktok" })];
    expect(bulkProblem([], tiktok, blankDrafts())).toBe(
      "Choose the clips to post.",
    );
    expect(bulkProblem([7], [], blankDrafts())).toBe(
      "Choose an account to post to.",
    );
    expect(bulkProblem([7], tiktok, blankDrafts())).toBe(
      "Choose who can see the TikTok posts.",
    );
    expect(bulkProblem([7], [socialAccount()], blankDrafts())).toBeNull();
    expect(postCountLabel(3, 2)).toBe("6 posts");
    expect(postCountLabel(1, 1)).toBe("1 post");
  });
});
