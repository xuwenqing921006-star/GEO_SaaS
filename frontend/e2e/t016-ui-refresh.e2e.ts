import { expect, test, type Page } from "@playwright/test";

const clientId = "00000000-0000-4000-8000-000000000101";

const signIn = async (page: Page): Promise<void> => {
  await page.goto(`/clients?clientId=${clientId}`);
  await page.getByLabel("用户名").fill("owner");
  await page.getByLabel("密码").fill("GeoSaaS2026!");
  await page.getByRole("button", { name: "登录" }).click();
};

const expectBrightShell = async (page: Page) => {
  const result = await page.evaluate(() => {
    const sidebar = document.querySelector<HTMLElement>(".sidebar");
    const root = getComputedStyle(document.documentElement);
    const color = sidebar ? getComputedStyle(sidebar).backgroundColor : "";
    const channels = color.match(/\d+/g)?.map(Number) ?? [];
    return {
      brightSidebar:
        channels.length >= 3 &&
        channels[0] > 235 &&
        channels[1] > 235 &&
        channels[2] > 235,
      pageToken: root.getPropertyValue("--page").trim(),
      actionToken: root.getPropertyValue("--action").trim(),
      navigationIcons: document.querySelectorAll(".nav-icon svg").length,
      overflow:
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    };
  });

  expect(result.brightSidebar).toBe(true);
  expect(result.pageToken).toBe("#f6f8f7");
  expect(result.actionToken).toBe("#2f6fec");
  expect(result.navigationIcons).toBe(7);
  return result;
};

test("all Web workspaces use the bright shell without horizontal overflow", async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await signIn(page);
  const paths = [
    "clients",
    "knowledge",
    "diagnostics",
    "strategy",
    "content",
    "channels",
    "settings",
  ];

  for (const width of [1440, 1280, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    for (const path of paths) {
      await page.goto(`/${path}?clientId=${clientId}`);
      await expect(page.locator("main")).toBeVisible();
      const result = await expectBrightShell(page);
      expect(
        result.overflow,
        `${path} 在 ${width}px 出现横向溢出：${result.scrollWidth}/${result.clientWidth}`,
      ).toBe(false);
    }
  }
  expect(pageErrors, "工作区切换过程中不应出现页面运行异常").toEqual([]);
});

test("knowledge editor is compact, clear, and keyboard dismissible", async ({
  page,
}) => {
  await signIn(page);
  await page.goto(`/knowledge?clientId=${clientId}`);
  await page.getByRole("button", { name: "编辑机构标准名称" }).click();

  const dialog = page.getByRole("dialog", { name: "编辑知识条目" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("知识标题")).toHaveValue("机构标准名称");
  await expect(
    dialog.getByRole("button", { name: "保存到知识库" }),
  ).toBeVisible();

  const geometry = await dialog.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return { width: rect.width, height: rect.height };
  });
  expect(geometry.width).toBeLessThanOrEqual(720);
  expect(geometry.height).toBeLessThan(760);

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect
    .poll(() => page.evaluate(() => document.body.style.overflow))
    .toBe("");
});

test("knowledge page removes review-oriented panels and keeps direct management actions", async ({
  page,
}) => {
  await signIn(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/knowledge?clientId=${clientId}`);
  await expect(
    page.getByRole("button", { name: "新增知识条目" }),
  ).toBeVisible();
  await expect(page.getByText("资料冲突")).toHaveCount(0);
  await expect(page.getByText("公开授权")).toHaveCount(0);
  await expect(page.getByText("禁用说法")).toHaveCount(0);
});

test("regular long-form modal keeps its actions visible at compact desktop height", async ({
  page,
}) => {
  await signIn(page);
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto(`/clients?clientId=${clientId}`);
  await page.getByRole("button", { name: "新建客户" }).click();

  const dialog = page.getByRole("dialog", { name: "新建客户" });
  const actions = dialog.locator(".modal-actions");
  await expect(dialog).toBeVisible();
  await expect(actions).toBeVisible();

  const geometry = await dialog.evaluate((element) => {
    const dialogRect = element.getBoundingClientRect();
    const actionsRect = element
      .querySelector<HTMLElement>(".modal-actions")
      ?.getBoundingClientRect();
    const body = element.querySelector<HTMLElement>(".modal-body");
    return {
      bodyScrolls: Boolean(body && body.scrollHeight > body.clientHeight),
      actionsVisible: Boolean(
        actionsRect &&
        actionsRect.top >= dialogRect.top &&
        actionsRect.bottom <= dialogRect.bottom,
      ),
    };
  });

  expect(geometry.bodyScrolls).toBe(true);
  expect(geometry.actionsVisible).toBe(true);
});
