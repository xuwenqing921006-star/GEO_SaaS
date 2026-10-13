import { expect, test } from "@playwright/test";

test("P08 uses the real settings API and fails closed without server encryption", async ({
  page,
}) => {
  await page.goto("/login?redirect=/settings");
  await page.getByLabel("用户名").fill("owner");
  await page.getByLabel("密码").fill("CorrectPassword2026!");
  await page.getByRole("button", { name: "登录" }).click();

  await expect(
    page.getByRole("heading", { name: "AI 引擎控制台" }),
  ).toBeVisible();
  await expect(page.getByText("0/ 4")).toBeVisible();
  await expect(page.getByText("qwen3.7-plus")).toBeVisible();
  await expect(page.getByText("deepseek-v4-pro")).toBeVisible();
  await expect(page.getByText("deepseek-v4-flash")).toBeVisible();

  const qwen = page.getByRole("article").filter({ hasText: "通义千问" });
  const secretInput = qwen.getByPlaceholder("粘贴密钥，保存后不可读取");
  await secretInput.fill("temporary-browser-test-key");
  await qwen.getByRole("checkbox", { name: "启用此引擎" }).check();
  await qwen.getByRole("button", { name: "保存配置" }).click();

  await expect(
    page.getByText("服务端尚未配置密钥保护能力，不能保存或使用模型密钥"),
  ).toBeVisible();
  await expect(secretInput).toHaveValue("");
  await expect(page.getByText("0/ 4")).toBeVisible();

  await page.getByLabel("默认单客户月度预算").fill("450");
  await page.getByRole("button", { name: "保存预算规则" }).click();
  await expect(page.getByText("默认客户月度预算已更新")).toBeVisible();
});
