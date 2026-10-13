import { describe, expect, it } from "vitest";

import {
  ARTICLE_COVER_STYLES,
  articleCoverUrl,
} from "../src/articleCoverLogic";

describe("article cover logic", () => {
  it("provides three bright cover styles", () => {
    expect(ARTICLE_COVER_STYLES.map((item) => item.value)).toEqual([
      "azure",
      "sunrise",
      "mint",
    ]);
  });

  it("builds encoded preview and download urls", () => {
    expect(articleCoverUrl("doc/1", "version 1", "sunrise", false)).toBe(
      "/api/v1/documents/doc%2F1/versions/version%201/cover?style=sunrise&render=v4-photo",
    );
    expect(
      articleCoverUrl("doc", "version", "mint", true, ["image-1", "image-2"]),
    ).toBe(
      "/api/v1/documents/doc/versions/version/cover?style=mint&render=v4-photo&images=image-1%2Cimage-2&download=true",
    );
  });
});
