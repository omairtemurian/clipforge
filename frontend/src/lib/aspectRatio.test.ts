import { describe, expect, it } from "vitest";
import { parseRatio } from "./aspectRatio";

describe("parseRatio", () => {
  it("accepts W:H in a few spellings and normalizes it", () => {
    expect(parseRatio("3:4")).toBe("3:4");
    expect(parseRatio(" 21 : 9 ")).toBe("21:9");
    expect(parseRatio("4x5")).toBe("4:5");
    expect(parseRatio("007:010")).toBe("7:10");
  });

  it("allows up to 4:1 either way", () => {
    expect(parseRatio("4:1")).toBe("4:1");
    expect(parseRatio("1:4")).toBe("1:4");
  });

  it.each(["", "9", "a:b", "0:5", "5:0", "1:5", "5:1", "1234:1", "3:4:5"])(
    "rejects %j",
    (text) => {
      expect(parseRatio(text)).toBeNull();
    },
  );
});
