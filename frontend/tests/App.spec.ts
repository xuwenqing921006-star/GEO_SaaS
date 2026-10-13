import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
} from "vitest";

import { mountApplication, resetApplicationRuntime } from "./fixtures/runtime";
import { server } from "./fixtures/api";

describe("Web production baseline", () => {
  let application: Awaited<ReturnType<typeof mountApplication>> | undefined;

  beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

  beforeEach(async () => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 1280,
    });
    window.dispatchEvent(new Event("resize"));
    application = await mountApplication();
  });

  afterEach(async () => {
    application?.wrapper.unmount();
    if (application) await resetApplicationRuntime(application);
    application = undefined;
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 1280,
    });
    window.dispatchEvent(new Event("resize"));
  });

  afterAll(() => server.close());

  it("identifies itself as the browser-only client", () => {
    const { wrapper } = application!;

    expect(wrapper.get("main").attributes("data-client")).toBe("web");
    expect(wrapper.text()).toContain("GEO SaaS");
    expect(wrapper.text()).toContain("Web");
    expect(
      wrapper.get('[data-client="web"]').find(".sr-only").text(),
    ).toContain("GEO SaaS Web");
  });
});
