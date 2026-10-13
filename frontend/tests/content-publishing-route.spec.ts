import { describe, expect, it } from "vitest";
import { router } from "../src/router";

describe("article publishing workspace route", () => {
  it("exposes a protected article publishing page with the current client", () => {
    const route = router.getRoutes().find((item) => item.name === "publishing");

    expect(route?.path).toBe("/publishing");
    expect(route?.meta.requiresAuth).toBe(true);
    expect(
      router.resolve({
        name: "publishing",
        query: { clientId: "client-1" },
      }).fullPath,
    ).toBe("/publishing?clientId=client-1");
  });
});
