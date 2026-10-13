import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/vue";
import { createPinia } from "pinia";
import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { http, HttpResponse } from "msw";

import App from "../src/App.vue";
import { router } from "../src/router";
import { useSessionStore } from "../src/stores/session";
import { useWorkspaceStore } from "../src/stores/workspace";
import {
  client,
  clientSummary,
  clientsPage,
  dashboard,
  errorResponse,
  server,
  session,
  successResponse,
} from "./fixtures/api";

const renderOwnerWorkspace = async () => {
  const pinia = createPinia();
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  useSessionStore(pinia).setSession(session);
  await router.replace(`/clients?clientId=${clientSummary.id}`);
  await router.isReady();
  render(App, {
    global: { plugins: [pinia, [VueQueryPlugin, { queryClient }], router] },
  });
  await screen.findByRole("heading", { name: "客户工作台" });
  return { pinia, queryClient };
};

const openDirtySwitch = async (): Promise<void> => {
  await fireEvent.click(
    await screen.findByRole("button", { name: "编辑莱恩美术" }),
  );
  await fireEvent.update(
    await screen.findByLabelText("企业名称"),
    "莱恩少儿美术",
  );
  await fireEvent.click(screen.getByRole("button", { name: "选择安心家政" }));
  await screen.findByRole("dialog", { name: "未保存的更改" });
};

const fillCreateForm = async (dialog: HTMLElement): Promise<void> => {
  for (const [label, value] of [
    ["企业名称", "重复客户"],
    ["行业代码", "art_education"],
    ["省份", "北京市"],
    ["城市", "北京市"],
    ["区县", "朝阳区"],
    ["详细地址", "望京路 1 号"],
    ["合作开始日期", "2026-01-01"],
  ]) {
    await fireEvent.update(
      dialog.querySelector(`[aria-label='${label}']`)!,
      value,
    );
  }
};

describe("T-002 high finding RED coverage", () => {
  beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

  beforeEach(() => {
    useSessionStore(createPinia()).setSession(null);
    server.use(
      http.get("/api/v1/clients", () => HttpResponse.json(clientsPage())),
      http.get("/api/v1/clients/:clientId", () =>
        HttpResponse.json(successResponse(client)),
      ),
      http.get("/api/v1/clients/:clientId/dashboard", () =>
        HttpResponse.json(dashboard()),
      ),
      http.patch("/api/v1/clients/:clientId", () =>
        HttpResponse.json(errorResponse(50001, "保存失败，请重试"), {
          status: 500,
        }),
      ),
      http.delete("/api/v1/auth/session", () =>
        HttpResponse.json(errorResponse(50001, "退出失败，请重试"), {
          status: 500,
        }),
      ),
      http.post("/api/v1/clients", () =>
        HttpResponse.json(
          errorResponse(40001, "请修正表单", [
            { field: "standard_name", message: "企业名称已存在" },
            { field: "industry_code", message: "行业代码无效" },
            { field: "province", message: "请选择省份" },
            { field: "city", message: "请选择城市" },
            { field: "district", message: "请选择区县" },
            { field: "address", message: "请填写详细地址" },
            { field: "cooperation_started_on", message: "请选择合作开始日期" },
          ]),
          { status: 400 },
        ),
      ),
    );
  });

  afterEach(async () => {
    cleanup();
    useSessionStore(createPinia()).setSession(null);
    await router.replace("/login");
    server.resetHandlers();
  });

  afterAll(() => server.close());

  it("renders level progress and next actions in the customer list", async () => {
    await renderOwnerWorkspace();

    const row = await screen.findByRole("row", { name: /莱恩美术/ });
    expect(within(row).getByText("可开始 GEO 工作")).toBeTruthy();
    expect(within(row).getByText("补充服务范围")).toBeTruthy();
  });

  it("keeps dirty state and offers a retry after a failed PATCH", async () => {
    await renderOwnerWorkspace();
    await openDirtySwitch();
    await fireEvent.click(screen.getByRole("button", { name: "保存并切换" }));

    const pendingDialog = await screen.findByRole("dialog", {
      name: "未保存的更改",
    });
    expect(pendingDialog).toBeTruthy();
    expect(
      (await within(pendingDialog).findByRole("alert")).textContent,
    ).toContain("保存失败，请重试");
    expect(screen.getByRole("button", { name: /重试/ })).toBeTruthy();
  });

  it("does not claim logout succeeded when DELETE fails", async () => {
    const { pinia } = await renderOwnerWorkspace();
    await fireEvent.click(screen.getByRole("button", { name: "账户菜单" }));
    await fireEvent.click(screen.getByRole("button", { name: "退出登录" }));

    expect(router.currentRoute.value.path).toBe("/clients");
    expect(useSessionStore(pinia).session).not.toBeNull();
    expect((await screen.findByRole("alert")).textContent).toContain(
      "退出失败，请重试",
    );
    expect(screen.getByRole("button", { name: /重试/ })).toBeTruthy();
  });

  it("enforces relogin_required by clearing session and cache before routing to login", async () => {
    server.use(
      http.put("/api/v1/auth/password", () =>
        HttpResponse.json(
          successResponse({ changed: true, relogin_required: true }),
        ),
      ),
    );
    const { pinia, queryClient } = await renderOwnerWorkspace();
    queryClient.setQueryData(["sensitive"], { value: true });
    await fireEvent.click(screen.getByRole("button", { name: "账户菜单" }));
    await fireEvent.click(screen.getByRole("button", { name: "修改密码" }));
    await fireEvent.update(
      screen.getByLabelText("当前密码"),
      "correct-password",
    );
    await fireEvent.update(
      screen.getByLabelText("新密码"),
      "new-correct-password",
    );
    await fireEvent.click(screen.getByRole("button", { name: "确认修改密码" }));

    await screen.findByRole("heading", { name: "负责人登录" });
    expect(useSessionStore(pinia).session).toBeNull();
    expect(queryClient.getQueryData(["sensitive"])).toBeUndefined();
  });

  it("maps 400 field errors to accessible required fields and a focusable summary", async () => {
    await renderOwnerWorkspace();
    await fireEvent.click(screen.getByRole("button", { name: "新建客户" }));
    const dialog = await screen.findByRole("dialog", { name: "新建客户" });
    await fillCreateForm(dialog);
    await fireEvent.click(screen.getByRole("button", { name: "创建客户" }));

    for (const label of [
      "企业名称",
      "行业代码",
      "省份",
      "城市",
      "区县",
      "详细地址",
      "合作开始日期",
    ]) {
      const field = screen.getByLabelText(label);
      expect(field.getAttribute("aria-invalid")).toBe("true");
      expect(field.getAttribute("aria-describedby")).toBeTruthy();
    }
    const summary = screen.getByRole("alert");
    expect(summary.getAttribute("tabindex")).toBe("-1");
    expect(summary).toBe(document.activeElement);
  });

  it("closes the save-and-switch dialog only after PATCH success and clears dirty state", async () => {
    server.use(
      http.patch(`/api/v1/clients/${clientSummary.id}`, () =>
        HttpResponse.json(
          successResponse({
            ...clientSummary,
            standard_name: "莱恩少儿美术",
            version: 2,
          }),
        ),
      ),
    );
    const { pinia } = await renderOwnerWorkspace();
    await openDirtySwitch();
    await fireEvent.click(screen.getByRole("button", { name: "保存并切换" }));

    await screen.findByRole("button", { name: "选择安心家政", pressed: true });
    expect(screen.queryByRole("dialog", { name: "未保存的更改" })).toBeNull();
    expect(useWorkspaceStore(pinia).isDirty).toBe(false);
  });

  it("locks every save-and-switch exit while the PATCH request is running", async () => {
    let releasePatch: (() => void) | undefined;
    const patchGate = new Promise<void>((resolve) => {
      releasePatch = resolve;
    });
    server.use(
      http.patch(`/api/v1/clients/${clientSummary.id}`, async () => {
        await patchGate;
        return HttpResponse.json(
          successResponse({
            ...clientSummary,
            standard_name: "莱恩少儿美术",
            version: 2,
          }),
        );
      }),
    );
    const { pinia } = await renderOwnerWorkspace();
    await openDirtySwitch();
    const pendingDialog = screen.getByRole("dialog", {
      name: "未保存的更改",
    });
    await fireEvent.click(
      within(pendingDialog).getByRole("button", {
        name: "保存并切换",
      }),
    );

    for (const name of ["关闭", "保存并切换", "放弃并切换", "取消"]) {
      expect(
        (
          within(pendingDialog).getByRole("button", {
            name,
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(true);
    }
    expect(
      screen
        .getByRole("button", { name: "选择莱恩美术" })
        .getAttribute("aria-pressed"),
    ).toBe("true");
    await router.push("/settings");
    expect(router.currentRoute.value.path).toBe("/clients");
    expect(useWorkspaceStore(pinia).pendingNavigation).toEqual({
      type: "client",
      clientId: "00000000-0000-4000-8000-000000000102",
    });

    releasePatch?.();
    await screen.findByRole("button", {
      name: "选择安心家政",
      pressed: true,
    });
    expect(screen.queryByRole("dialog", { name: "未保存的更改" })).toBeNull();
  });

  it("blocks dirty query navigation and logout behind the same discard dialog", async () => {
    await renderOwnerWorkspace();
    await fireEvent.click(
      await screen.findByRole("button", { name: "编辑莱恩美术" }),
    );
    await fireEvent.update(
      await screen.findByLabelText("企业名称"),
      "莱恩少儿美术",
    );

    await router.push("/clients?clientId=00000000-0000-4000-8000-000000000102");
    const queryNavigationPrompt = screen.queryByRole("dialog", {
      name: "未保存的更改",
    });
    await fireEvent.click(screen.getByRole("button", { name: "账户菜单" }));
    await fireEvent.click(screen.getByRole("button", { name: "退出登录" }));
    const logoutPrompt = screen.queryByRole("dialog", { name: "未保存的更改" });

    expect(queryNavigationPrompt).toBeTruthy();
    expect(logoutPrompt).toBeTruthy();
  });

  it("routes mock GET, DELETE, and password PUT by method and invalidates its session", async () => {
    const { mockRequest } = await import("../src/api/mock");
    await mockRequest("/api/v1/auth/login", { method: "POST" });
    expect(
      (await mockRequest("/api/v1/auth/session", { method: "GET" })).ok,
    ).toBe(true);
    expect(
      (await mockRequest("/api/v1/auth/session", { method: "DELETE" })).ok,
    ).toBe(true);
    expect(
      (await mockRequest("/api/v1/auth/session", { method: "GET" })).status,
    ).toBe(401);
    await mockRequest("/api/v1/auth/login", { method: "POST" });
    await mockRequest("/api/v1/auth/password", { method: "PUT" });
    expect(
      (await mockRequest("/api/v1/auth/session", { method: "GET" })).status,
    ).toBe(401);
  });

  it("restores only the development Mock login marker after a module reload", async () => {
    sessionStorage.clear();
    vi.resetModules();
    const firstMock = await import("../src/api/mock");
    await firstMock.mockRequest("/api/v1/auth/login", { method: "POST" });

    expect(sessionStorage.length).toBe(1);
    expect(sessionStorage.key(0)).toContain("dev_mock_authenticated");
    expect(sessionStorage.getItem(sessionStorage.key(0) ?? "")).toBe("1");

    vi.resetModules();
    const reloadedMock = await import("../src/api/mock");
    expect(
      (
        await reloadedMock.mockRequest("/api/v1/auth/session", {
          method: "GET",
        })
      ).ok,
    ).toBe(true);

    await reloadedMock.mockRequest("/api/v1/auth/session", {
      method: "DELETE",
    });
    expect(sessionStorage.length).toBe(0);
  });

  it("keeps archive conflicts and restore failures recoverable", async () => {
    server.use(
      http.post(`/api/v1/clients/${clientSummary.id}/archive`, () =>
        HttpResponse.json(errorResponse(40901, "客户已更新，请刷新后重试"), {
          status: 409,
        }),
      ),
    );
    await renderOwnerWorkspace();
    await fireEvent.click(
      await screen.findByRole("button", { name: "删除莱恩美术" }),
    );
    await fireEvent.update(screen.getByLabelText("删除原因"), "合作暂停");
    await fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
    const archiveAlert = await screen.findByRole("alert");
    const archiveRetry = screen.queryByRole("button", { name: /重试/ });
    await waitFor(() =>
      expect(
        (
          screen.getByRole("button", {
            name: "确认删除",
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(false),
    );

    await fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    let lifecycleClient = { ...client };
    server.use(
      http.get("/api/v1/clients", ({ request }) => {
        const status = new URL(request.url).searchParams.get("status");
        return HttpResponse.json(
          clientsPage(
            status === "archived" && lifecycleClient.status === "archived"
              ? [lifecycleClient]
              : status === "archived"
                ? []
                : lifecycleClient.status === "archived"
                  ? []
                  : [lifecycleClient],
          ),
        );
      }),
      http.post(`/api/v1/clients/${clientSummary.id}/archive`, () =>
        HttpResponse.json(
          successResponse(
            (lifecycleClient = {
              ...lifecycleClient,
              status: "archived",
              version: 2,
            }),
          ),
        ),
      ),
      http.post(`/api/v1/clients/${clientSummary.id}/restore`, () =>
        HttpResponse.json(errorResponse(50001, "恢复失败，请重试"), {
          status: 500,
        }),
      ),
    );
    await fireEvent.click(screen.getByRole("button", { name: "删除莱恩美术" }));
    await fireEvent.update(screen.getByLabelText("删除原因"), "合作暂停");
    await fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
    await fireEvent.update(screen.getByLabelText("状态"), "archived");
    await fireEvent.click(
      await screen.findByRole("button", { name: "恢复莱恩美术" }),
    );

    expect(archiveAlert?.textContent ?? "").toContain(
      "客户已更新，请刷新后重试",
    );
    expect(archiveRetry).toBeTruthy();
    expect(await screen.findByText("恢复失败，请重试")).toBeTruthy();
  });

  it("recomputes pagination after deleting the last record from the next page", async () => {
    let archived = false;
    const inventory = Array.from({ length: 21 }, (_, index) =>
      index === 0
        ? clientSummary
        : {
            ...clientSummary,
            id: `00000000-0000-4000-8000-${String(200 + index).padStart(12, "0")}`,
            standard_name: `分页客户 ${index}`,
          },
    );
    server.use(
      http.get("/api/v1/clients", () => {
        const items = archived
          ? inventory.slice(1, 21)
          : inventory.slice(0, 20);
        return HttpResponse.json(
          successResponse({
            items,
            page: 1,
            page_size: 20,
            total: archived ? 20 : 21,
            has_next: !archived,
          }),
        );
      }),
      http.post(`/api/v1/clients/${clientSummary.id}/archive`, () => {
        archived = true;
        return HttpResponse.json(
          successResponse({
            ...clientSummary,
            status: "archived",
            version: 2,
          }),
        );
      }),
    );
    await renderOwnerWorkspace();
    await waitFor(() =>
      expect(
        (screen.getByRole("button", { name: "下一页" }) as HTMLButtonElement)
          .disabled,
      ).toBe(false),
    );

    await fireEvent.click(screen.getByRole("button", { name: "删除莱恩美术" }));
    await fireEvent.update(screen.getByLabelText("删除原因"), "合作暂停");
    await fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    await waitFor(() =>
      expect(
        (screen.getByRole("button", { name: "下一页" }) as HTMLButtonElement)
          .disabled,
      ).toBe(true),
    );
  });

  it("returns to the default managed-customer list after creating from the deleted filter", async () => {
    const createdClient = {
      ...clientSummary,
      id: "00000000-0000-4000-8000-000000000109",
      standard_name: "重复客户",
    };
    let created = false;
    server.use(
      http.get("/api/v1/clients", ({ request }) => {
        const status = new URL(request.url).searchParams.get("status");
        return HttpResponse.json(
          clientsPage(
            status === "archived"
              ? []
              : created
                ? [createdClient, clientSummary]
                : [clientSummary],
          ),
        );
      }),
      http.post("/api/v1/clients", () => {
        created = true;
        return HttpResponse.json(successResponse(createdClient, 201), {
          status: 201,
        });
      }),
    );
    await renderOwnerWorkspace();
    await fireEvent.update(screen.getByLabelText("状态"), "archived");
    await screen.findByText("暂无客户");
    await fireEvent.click(screen.getByRole("button", { name: "新建客户" }));
    const createDialog = await screen.findByRole("dialog", {
      name: "新建客户",
    });
    await fillCreateForm(createDialog);
    await fireEvent.click(
      within(createDialog).getByRole("button", { name: "创建客户" }),
    );

    await waitFor(() =>
      expect(router.currentRoute.value.query.status).toBeUndefined(),
    );
    expect(
      await screen.findByRole("button", { name: "选择重复客户" }),
    ).toBeTruthy();
  });

  it("shows a general retryable error for a 500 create response without field_errors", async () => {
    server.use(
      http.post("/api/v1/clients", () =>
        HttpResponse.json(errorResponse(50001, "服务暂时不可用"), {
          status: 500,
        }),
      ),
    );
    await renderOwnerWorkspace();
    await fireEvent.click(screen.getByRole("button", { name: "新建客户" }));
    const dialog = await screen.findByRole("dialog", { name: "新建客户" });
    await fillCreateForm(dialog);
    await fireEvent.click(screen.getByRole("button", { name: "创建客户" }));

    expect(await screen.findByText("创建失败，请重试")).toBeTruthy();
  });

  it("does not carry a failed password retry into the account dialog", async () => {
    const methods: string[] = [];
    server.use(
      http.put("/api/v1/auth/password", ({ request }) => {
        methods.push(request.method);
        return HttpResponse.json(errorResponse(50001, "修改密码失败，请重试"), {
          status: 500,
        });
      }),
      http.delete("/api/v1/auth/session", ({ request }) => {
        methods.push(request.method);
        return HttpResponse.json(successResponse({ logged_out: true }));
      }),
    );
    await renderOwnerWorkspace();
    await fireEvent.click(screen.getByRole("button", { name: "账户菜单" }));
    await fireEvent.click(screen.getByRole("button", { name: "修改密码" }));
    await fireEvent.update(screen.getByLabelText("当前密码"), "old-password");
    await fireEvent.update(screen.getByLabelText("新密码"), "new-password");
    await fireEvent.click(screen.getByRole("button", { name: "确认修改密码" }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "修改密码失败，请重试",
    );

    await fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    await fireEvent.click(screen.getByRole("button", { name: "账户菜单" }));

    expect(screen.queryByRole("alert")).toBeNull();
    expect(
      screen.queryByRole("button", {
        name: "重试",
      }),
    ).toBeNull();
    expect(methods).toEqual(["PUT"]);
  });

  it("retries a failed password-dialog DELETE with DELETE only, never PUT", async () => {
    const methods: string[] = [];
    server.use(
      http.delete("/api/v1/auth/session", ({ request }) => {
        methods.push(request.method);
        return HttpResponse.json(errorResponse(50001, "退出失败，请重试"), {
          status: 500,
        });
      }),
      http.put("/api/v1/auth/password", ({ request }) => {
        methods.push(request.method);
        return HttpResponse.json(
          successResponse({ changed: true, relogin_required: false }),
        );
      }),
    );
    await renderOwnerWorkspace();
    await fireEvent.click(screen.getByRole("button", { name: "账户菜单" }));
    await fireEvent.click(screen.getByRole("button", { name: "修改密码" }));
    await fireEvent.click(screen.getByRole("button", { name: "退出登录" }));
    await fireEvent.click(await screen.findByRole("button", { name: "重试" }));

    expect(methods).toEqual(["DELETE", "DELETE"]);
  });
});
