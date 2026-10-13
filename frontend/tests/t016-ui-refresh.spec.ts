import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";

import ModalDialog from "../src/components/ModalDialog.vue";

describe("T-016 shared modal system", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    document.body.style.overflow = "";
  });

  it("renders a labelled size variant and restores page scrolling", async () => {
    const wrapper = mount(ModalDialog, {
      attachTo: document.body,
      props: { title: "证据与授权", size: "large" },
      slots: { default: "<button type='button'>保存</button>" },
    });

    const dialog = document.body.querySelector<HTMLElement>("[role=dialog]");
    expect(dialog).not.toBeNull();
    expect(dialog?.classList.contains("modal--large")).toBe(true);
    expect(dialog?.getAttribute("aria-labelledby")).toBeTruthy();
    expect(document.body.style.overflow).toBe("hidden");

    await wrapper.unmount();
    expect(document.body.style.overflow).toBe("");
  });

  it("closes on Escape and exposes a clear close action", async () => {
    const wrapper = mount(ModalDialog, {
      attachTo: document.body,
      props: { title: "账户菜单", size: "small" },
      slots: { default: "<p>账户操作</p>" },
    });

    expect(document.body.querySelector(".modal--small")).not.toBeNull();
    expect(
      document.body.querySelector("button[aria-label='关闭']"),
    ).not.toBeNull();

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(wrapper.emitted("close")).toHaveLength(1);
    wrapper.unmount();
  });
});
