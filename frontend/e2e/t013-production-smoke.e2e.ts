import { expect, test } from "@playwright/test";

const username = process.env.T013_OWNER_USERNAME;
const password = process.env.T013_OWNER_PASSWORD;

test.skip(
  !username || !password,
  "T013_OWNER_USERNAME and T013_OWNER_PASSWORD are required",
);

test("production HTTPS stack is secure, ready, and usable", async ({
  page,
  request,
}) => {
  const ready = await request.get("/api/v1/health/ready");
  expect(ready.status()).toBe(200);
  expect((await ready.json()).data).toMatchObject({
    status: "ready",
    database: "ok",
    storage: "ok",
    worker_heartbeat: "ok",
  });
  expect(ready.headers()["strict-transport-security"]).toContain(
    "max-age=31536000",
  );
  expect(ready.headers()["content-security-policy"]).toContain(
    "default-src 'self'",
  );
  expect(ready.headers()["x-content-type-options"]).toBe("nosniff");
  expect(ready.headers()["x-frame-options"]).toBe("DENY");
  expect(ready.headers()["referrer-policy"]).toBe("no-referrer");

  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "负责人登录" })).toBeVisible();
  await page.getByLabel("用户名").fill(username ?? "");
  await page.getByLabel("密码").fill(password ?? "");
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/clients/);
  await expect(page.getByRole("heading", { name: "客户工作台" })).toBeVisible();
  await expect(page.getByText("暂无客户")).toBeVisible();
});
