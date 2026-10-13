import { createRouter, createWebHistory } from "vue-router";
import { hasSession, initializeRememberedSession } from "../stores/session";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("../views/LoginView.vue"),
      meta: { guestOnly: true },
    },
    {
      path: "/clients",
      name: "clients",
      component: () => import("../views/ClientsView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/knowledge",
      name: "knowledge",
      component: () => import("../views/KnowledgeView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/diagnostics",
      name: "diagnostics",
      component: () => import("../views/DiagnosticsView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/strategy",
      name: "strategy",
      component: () => import("../views/StrategyView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/content",
      name: "content",
      component: () => import("../views/ContentView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/publishing",
      name: "publishing",
      component: () => import("../views/ArticlePublishingView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/channels",
      name: "channels",
      component: () => import("../views/ChannelsView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/monitoring",
      name: "monitoring",
      redirect: (to) => ({ name: "diagnostics", query: to.query }),
    },
    {
      path: "/settings",
      name: "settings",
      component: () => import("../views/SettingsView.vue"),
      meta: { requiresAuth: true },
    },
    { path: "/:pathMatch(.*)*", redirect: "/clients" },
  ],
});

router.beforeEach(async (to) => {
  await initializeRememberedSession();
  if (to.meta.requiresAuth && !hasSession())
    return { name: "login", query: { redirect: to.fullPath } };
  if (to.meta.guestOnly && hasSession()) return "/clients";
  return true;
});
