import { expect, test, type Page } from "@playwright/test";

const clientId = "00000000-0000-4000-8000-000000000101";

const signIn = async (page: Page): Promise<void> => {
  await page.goto(`/channels?clientId=${clientId}`);
  await page.getByLabel("用户名").fill("owner");
  await page.getByLabel("密码").fill("GeoSaaS2026!");
  await page.getByRole("button", { name: "登录" }).click();
};

const expectNoPageOverflow = async (page: Page): Promise<void> => {
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    )
    .toBe(true);
};

test("publishing configuration exposes the four platforms and five-account limit", async ({
  page,
}) => {
  await signIn(page);
  await expect(
    page.getByRole("heading", { name: "发布账号", level: 1 }),
  ).toBeVisible();
  await expect(page.getByText("每个平台最多连接 5 个账号")).toBeVisible();
  await expect(page.getByText("不保存账号密码")).toBeVisible();
  await expect(
    page.getByText("每个账号保留独立的本机浏览器会话"),
  ).toBeVisible();

  for (const platform of ["头条号", "百家号", "网易号", "搜狐号"]) {
    await expect(
      page.getByRole("heading", { name: platform, level: 2 }),
    ).toBeVisible();
  }
  await expect(page.getByRole("button", { name: "添加账号" })).toHaveCount(4);
  await expect(page.getByRole("link", { name: "打开后台 ↗" })).toHaveCount(4);
  await expect(page.getByLabel(/账号密码/)).toHaveCount(0);
});

test("GEO diagnostics use API answers and never turn missing samples into zero", async ({
  page,
}) => {
  await signIn(page);
  await page.goto(`/monitoring?clientId=${clientId}`);
  await expect(page).toHaveURL(
    new RegExp(`/diagnostics\\?clientId=${clientId}`),
  );
  await expect(
    page.getByRole("heading", { name: "GEO 诊断", level: 1 }),
  ).toBeVisible();
  await expect(
    page.getByText("当前没有可用于评分的自动检测回答"),
  ).toBeVisible();
  await expect(
    page.getByText("系统调用各平台官方 API", { exact: false }),
  ).toBeVisible();
  await expect(page.getByText("消费者端人工")).toHaveCount(0);
  await expect(page.getByText("综合评分", { exact: true })).toBeVisible();
  await expect(page.locator(".diagnosis-score > strong")).toHaveText("—");
});

test("configured API keys are masked and never rendered as plaintext", async ({
  page,
}) => {
  await signIn(page);
  await page.goto(`/settings?clientId=${clientId}`);
  await expect(
    page.getByRole("heading", { name: "AI 引擎控制台", level: 1 }),
  ).toBeVisible();
  const deepseekCard = page.locator(".provider-deepseek");
  await expect(deepseekCard.getByText("连接已验证")).toBeVisible();
  await expect(deepseekCard.getByText("当前 ••••7K2Q")).toBeVisible();
  await expect(page.getByText("sk-real-secret-value")).toHaveCount(0);
  await expect(
    page.getByText("浏览器不保存，也不会再次读取明文"),
  ).toBeVisible();
});

test("publishing, diagnostics, and settings remain readable at supported desktop widths", async ({
  page,
}) => {
  await signIn(page);
  const pages = [
    ["channels", "发布账号"],
    ["diagnostics", "GEO 诊断"],
    ["settings", "AI 引擎控制台"],
  ] as const;

  for (const width of [1440, 1280, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    for (const [path, heading] of pages) {
      await page.goto(`/${path}?clientId=${clientId}`);
      await expect(
        page.getByRole("heading", { name: heading, level: 1 }),
      ).toBeVisible();
      await expectNoPageOverflow(page);
    }
  }
});
