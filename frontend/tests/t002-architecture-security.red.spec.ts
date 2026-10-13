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
} from "vitest";
import { http, HttpResponse } from "msw";

import App from "../src/App.vue";
import CreateClientForm from "../src/components/CreateClientForm.vue";
import { router } from "../src/router";
import { useSessionStore } from "../src/stores/session";
import { useWorkspaceStore } from "../src/stores/workspace";
import {
  apiRequests,
  client,
  clientSummary,
  clientsPage,
  dashboard,
  secondClient,
  server,
  session,
  successResponse,
} from "./fixtures/api";

const renderWithApplicationRuntime = async (
  path: string,
  hasSession = false,
) => {
  const pinia = createPinia();
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  useSessionStore(pinia).setSession(hasSession ? session : null);
  await router.replace(path);
  await router.isReady();
  render(App, {
    global: {
      plugins: [pinia, [VueQueryPlugin, { queryClient }], router],
    },
  });
  return { pinia, queryClient };
};

const useRestoredSession = (): void => {
  server.use(
    http.get("/api/v1/auth/session", () =>
      HttpResponse.json(successResponse(session)),
    ),
  );
};

describe("T-002 architecture and security RED coverage", () => {
  beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

  beforeEach(() => {
    apiRequests.length = 0;
    useSessionStore(createPinia()).setSession(null);
    server.use(
      http.get("/api/v1/clients", () => HttpResponse.json(clientsPage())),
      http.get("/api/v1/clients/:clientId/dashboard", () =>
        HttpResponse.json(dashboard()),
      ),
      http.get("/api/v1/clients/:clientId", ({ params }) =>
        HttpResponse.json(
          successResponse(
            params.clientId === secondClient.id
              ? {
                  ...client,
                  ...secondClient,
                }
              : client,
          ),
        ),
      ),
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(successResponse(session)),
      ),
      http.post("/api/v1/clients", () =>
        HttpResponse.json(successResponse(client, 201), { status: 201 }),
      ),
    );
  });

  afterEach(() => {
    cleanup();
    server.resetHandlers();
  });

  afterAll(() => server.close());

  it("uses a real Router, one Pinia instance, and one QueryClient to redirect an unauthenticated deep link", async () => {
    const { pinia, queryClient } = await renderWithApplicationRuntime(
      "/clients?clientId=00000000-0000-4000-8000-000000000101&page=2",
    );

    expect(router.currentRoute.value.path).toBe("/login");
    expect(router.currentRoute.value.query.redirect).toBe(
      "/clients?clientId=00000000-0000-4000-8000-000000000101&page=2",
    );
    expect(useSessionStore(pinia).session).toBeNull();
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    expect(
      await screen.findByRole("heading", { name: "负责人登录" }),
    ).toBeTruthy();
  });

  it("restores a valid session to the original deep link rather than leaving the owner on login", async () => {
    useRestoredSession();
    const deepLink =
      "/clients?clientId=00000000-0000-4000-8000-000000000101&page=2";
    await renderWithApplicationRuntime(deepLink);

    await screen.findByRole("heading", { name: "客户工作台" });
    expect(router.currentRoute.value.fullPath).toBe(deepLink);
  });

  it("uses router navigation for login and clears the shared client cache on a 401", async () => {
    const { queryClient } = await renderWithApplicationRuntime(
      "/login?redirect=/clients?page=2",
    );
    queryClient.setQueryData(["clients", { page: 2 }], clientsPage());

    await screen.findByRole("heading", { name: "负责人登录" });
    await fireEvent.update(screen.getByLabelText("用户名"), "owner");
    await fireEvent.update(screen.getByLabelText("密码"), "correct-password");
    await fireEvent.click(screen.getByRole("button", { name: "登录" }));
    await screen.findByRole("heading", { name: "客户工作台" });
    expect(router.currentRoute.value.fullPath).toBe("/clients?page=2");

    window.dispatchEvent(new CustomEvent("geo:unauthorized"));
    await waitFor(() => expect(router.currentRoute.value.path).toBe("/login"));
    expect(queryClient.getQueryData(["clients", { page: 2 }])).toBeUndefined();
  });

  it("shows the current customer and its GEO task from the initial clientId URL", async () => {
    useRestoredSession();
    await renderWithApplicationRuntime(
      `/clients?clientId=${clientSummary.id}`,
      true,
    );

    expect(screen.queryByText("选择客户查看工作台")).toBeNull();
    expect(
      await screen.findByRole("button", {
        name: "选择莱恩美术",
        pressed: true,
      }),
    ).toBeTruthy();
    const row = screen.getByRole("row", { name: /莱恩美术/ });
    expect(within(row).getByText("补充服务范围")).toBeTruthy();
  });

  it("selects a newly created customer in the integrated customer list", async () => {
    const created = {
      ...client,
      id: "00000000-0000-4000-8000-000000000103",
      standard_name: "新建客户",
    };
    server.use(
      http.post("/api/v1/clients", () =>
        HttpResponse.json(successResponse(created, 201), { status: 201 }),
      ),
    );
    useRestoredSession();
    await renderWithApplicationRuntime("/clients", true);
    await screen.findByRole("heading", { name: "客户工作台" });
    await fireEvent.click(screen.getByRole("button", { name: "新建客户" }));
    await fireEvent.update(
      screen.getByLabelText("企业名称"),
      created.standard_name,
    );
    await fireEvent.update(
      screen.getByLabelText("行业代码"),
      created.industry_code,
    );
    await fireEvent.update(screen.getByLabelText("省份"), created.province);
    await fireEvent.update(screen.getByLabelText("城市"), created.city);
    await fireEvent.update(screen.getByLabelText("区县"), created.district);
    await fireEvent.update(screen.getByLabelText("详细地址"), created.address);
    await fireEvent.update(
      screen.getByLabelText("合作开始日期"),
      created.cooperation_started_on,
    );
    await fireEvent.click(screen.getByRole("button", { name: "创建客户" }));

    expect(
      await screen.findByRole("button", {
        name: "选择新建客户",
        pressed: true,
      }),
    ).toBeTruthy();
  });

  it("manages q, status, sort, page, page_size, and clientId through router query plus history", async () => {
    useRestoredSession();
    const firstUrl = `/clients?q=莱恩&status=active&sort=standard_name&page=2&page_size=50&clientId=${clientSummary.id}`;
    await renderWithApplicationRuntime(firstUrl, true);
    await screen.findByRole("heading", { name: "客户工作台" });

    expect(
      (screen.getByRole("searchbox", { name: "搜索客户" }) as HTMLInputElement)
        .value,
    ).toBe("莱恩");
    expect((screen.getByLabelText("状态") as HTMLSelectElement).value).toBe(
      "active",
    );
    expect((screen.getByLabelText("排序") as HTMLSelectElement).value).toBe(
      "standard_name",
    );
    expect(
      apiRequests.some(
        (url) =>
          url.searchParams.get("q") === "莱恩" &&
          url.searchParams.get("status") === "active" &&
          url.searchParams.get("sort") === "standard_name" &&
          url.searchParams.get("page") === "2" &&
          url.searchParams.get("page_size") === "50",
      ),
    ).toBe(true);

    await router.push(
      `/clients?q=安心&status=paused&page=3&page_size=10&clientId=${secondClient.id}`,
    );
    await waitFor(() =>
      expect(
        (
          screen.getByRole("searchbox", {
            name: "搜索客户",
          }) as HTMLInputElement
        ).value,
      ).toBe("安心"),
    );
    await router.back();
    await waitFor(() =>
      expect(
        (
          screen.getByRole("searchbox", {
            name: "搜索客户",
          }) as HTMLInputElement
        ).value,
      ).toBe("莱恩"),
    );
    expect(screen.getByRole("button", { name: "下一页" })).toBeTruthy();
  });

  it("keeps dirty state in Pinia, PATCHes the versioned client before save-and-switch, and guards router leave", async () => {
    const patchBodies: unknown[] = [];
    server.use(
      http.patch(`/api/v1/clients/${clientSummary.id}`, async ({ request }) => {
        patchBodies.push(await request.json());
        return HttpResponse.json(
          successResponse({
            ...client,
            standard_name: "莱恩少儿美术",
            version: 2,
          }),
        );
      }),
    );
    useRestoredSession();
    const { pinia } = await renderWithApplicationRuntime(
      `/clients?clientId=${clientSummary.id}`,
      true,
    );
    await screen.findByRole("button", { name: "编辑莱恩美术" });
    await fireEvent.click(screen.getByRole("button", { name: "编辑莱恩美术" }));
    await fireEvent.update(
      await screen.findByLabelText("企业名称"),
      "莱恩少儿美术",
    );
    expect(useWorkspaceStore(pinia).isDirty).toBe(true);

    await router.push("/settings");
    expect(router.currentRoute.value.fullPath).not.toBe("/settings");
    const pendingDialog = await screen.findByRole("dialog", {
      name: "未保存的更改",
    });
    await fireEvent.click(
      within(pendingDialog).getByRole("button", { name: "取消" }),
    );

    await fireEvent.click(screen.getByRole("button", { name: "选择安心家政" }));
    await fireEvent.click(
      await screen.findByRole("button", { name: "保存并切换" }),
    );

    await waitFor(() =>
      expect(patchBodies).toContainEqual(
        expect.objectContaining({
          version: 1,
          standard_name: "莱恩少儿美术",
          address: client.address,
          cooperation_started_on: client.cooperation_started_on,
        }),
      ),
    );
    expect(useWorkspaceStore(pinia).isDirty).toBe(false);
    await router.push("/settings");
    expect(router.currentRoute.value.fullPath).toBe("/settings");
  });

  it("supports owner logout and password change through the documented CSRF-protected endpoints", async () => {
    const requestMethods: string[] = [];
    server.use(
      http.delete("/api/v1/auth/session", ({ request }) => {
        requestMethods.push(request.method);
        return HttpResponse.json(successResponse({ logged_out: true }));
      }),
      http.put("/api/v1/auth/password", ({ request }) => {
        requestMethods.push(request.method);
        return HttpResponse.json(
          successResponse({ changed: true, relogin_required: true }),
        );
      }),
    );
    useRestoredSession();
    await renderWithApplicationRuntime("/clients", true);

    await fireEvent.click(
      await screen.findByRole("button", { name: "账户菜单" }),
    );
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
    await fireEvent.click(screen.getByRole("button", { name: "退出登录" }));

    await waitFor(() =>
      expect(requestMethods).toEqual(expect.arrayContaining(["PUT", "DELETE"])),
    );
    await waitFor(() => expect(router.currentRoute.value.path).toBe("/login"));
  });

  it("archives and restores a client through versioned customer lifecycle requests", async () => {
    const lifecycleRequests: string[] = [];
    let lifecycleClient = { ...client };
    server.use(
      http.get("/api/v1/clients", ({ request }) => {
        const status = new URL(request.url).searchParams.get("status");
        const items =
          status === "archived" && lifecycleClient.status === "archived"
            ? [lifecycleClient]
            : status === "archived"
              ? []
              : lifecycleClient.status === "archived"
                ? [secondClient]
                : [lifecycleClient, secondClient];
        return HttpResponse.json(clientsPage(items));
      }),
      http.post(
        `/api/v1/clients/${clientSummary.id}/archive`,
        ({ request }) => {
          lifecycleRequests.push(
            `${request.method} ${new URL(request.url).pathname}`,
          );
          lifecycleClient = {
            ...lifecycleClient,
            status: "archived",
            version: 2,
          };
          return HttpResponse.json(successResponse(lifecycleClient));
        },
      ),
      http.post(
        `/api/v1/clients/${clientSummary.id}/restore`,
        ({ request }) => {
          lifecycleRequests.push(
            `${request.method} ${new URL(request.url).pathname}`,
          );
          lifecycleClient = {
            ...lifecycleClient,
            status: "active",
            version: 3,
          };
          return HttpResponse.json(successResponse(lifecycleClient));
        },
      ),
    );
    useRestoredSession();
    await renderWithApplicationRuntime(
      `/clients?clientId=${clientSummary.id}`,
      true,
    );

    await fireEvent.click(
      await screen.findByRole("button", { name: "删除莱恩美术" }),
    );
    await fireEvent.update(screen.getByLabelText("删除原因"), "合作暂停");
    await fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
    await fireEvent.update(screen.getByLabelText("状态"), "archived");
    await fireEvent.click(
      await screen.findByRole("button", { name: "恢复莱恩美术" }),
    );

    await waitFor(() =>
      expect(lifecycleRequests).toEqual([
        `POST /api/v1/clients/${clientSummary.id}/archive`,
        `POST /api/v1/clients/${clientSummary.id}/restore`,
      ]),
    );
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "恢复莱恩美术" })).toBeNull(),
    );
    expect(router.currentRoute.value.query.status).toBe("archived");
  });

  it("fails safe: mock traffic is enabled only by explicit VITE_USE_MOCK=true", async () => {
    const httpModule = (await import("../src/api/http")) as {
      shouldUseMock?: (
        environment: Record<string, string | undefined>,
      ) => boolean;
    };

    expect(httpModule.shouldUseMock).toBeTypeOf("function");
    expect(httpModule.shouldUseMock?.({ MODE: "production" })).toBe(false);
    expect(
      httpModule.shouldUseMock?.({
        MODE: "production",
        VITE_USE_MOCK: "false",
      }),
    ).toBe(false);
    expect(
      httpModule.shouldUseMock?.({ MODE: "production", VITE_USE_MOCK: "true" }),
    ).toBe(true);
  });

  it("marks invalid creation fields, moves focus to the first error, and restores trigger focus after a modal closes", async () => {
    render(CreateClientForm, {
      props: { submitting: false, serverErrors: {} },
    });
    await fireEvent.click(screen.getByRole("button", { name: "创建客户" }));
    const nameField = screen.getByLabelText("企业名称");
    expect(nameField.getAttribute("aria-invalid")).toBe("true");
    expect(nameField).toBe(document.activeElement);
    cleanup();

    useRestoredSession();
    await renderWithApplicationRuntime("/clients", true);
    const trigger = await screen.findByRole("button", { name: "新建客户" });
    await fireEvent.click(trigger);
    await screen.findByRole("dialog", { name: "新建客户" });
    await fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "新建客户" })).toBeNull(),
    );
    expect(trigger).toBe(document.activeElement);
  });
});
