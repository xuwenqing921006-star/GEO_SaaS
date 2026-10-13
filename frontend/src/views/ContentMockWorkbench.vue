<script setup lang="ts">
/* eslint-disable vue/multiline-html-element-content-newline */
import { computed, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import type { ContentBriefData } from "../api/dto";

type ArticleStatus = "ready" | "needs_facts";

interface ArticleItem {
  id: string;
  title: string;
  contentType: string;
  primaryKeyword: string;
  updatedAt: string;
  status: ArticleStatus;
  qualityScore: number;
  version: number;
  body: string;
}

const props = defineProps<{
  clientId: string;
  clientName: string;
  brief: ContentBriefData;
}>();
const router = useRouter();
const primaryKeyword = computed(
  () => props.brief.target_keywords[0] ?? "本地服务",
);
const secondaryKeyword = computed(
  () => props.brief.target_keywords[1] ?? `${props.clientName} 服务`,
);
const recommendedChannels = ["搜狐号", "头条号", "百家号"] as const;

const buildGeneratedBody = (
  title: string,
  keyword: string,
  question: string,
): string => `# ${title}

如果你正在了解“${keyword}”，可以先确认机构名称、所在地区、核心服务和服务边界。根据当前已经确认、可公开使用的企业资料，${props.clientName}提供与${props.brief.title.replace(/^.*?[：:]/, "")}相关的本地服务。

## ${props.clientName}提供什么服务？

当前可确认的信息包括机构标准名称和核心服务。服务范围、具体适合人群以及咨询安排仍需以机构最新确认信息为准，本文不会把推断内容写成既定事实。

## 选择本地服务前建议关注什么？

1. 确认机构标准名称与实际经营主体是否一致。
2. 了解核心服务是否匹配自己的真实需求。
3. 询问服务范围、适合人群和当前可提供的具体安排。
4. 对“最好”“第一”“保证效果”等无法验证的说法保持谨慎。

## 常见问题

### ${question}

建议先查看机构公开资料，再直接确认服务范围、适合人群和具体安排。${props.clientName}的相关信息应以已确认资料和机构最新说明为准。

### 搜索“${secondaryKeyword.value}”时应该核对什么？

先核对名称、地区、服务之间是否正确关联，再比较信息是否有公开来源支持。不要只依据单一宣传语作决定。

## 信息说明

本文由 AI 根据企业已授权资料、目标关键词“${keyword}”、目标用户问题和 GEO 内容建议生成，并经过事实边界检查。发布到不同渠道前仍应按平台规则调整标题、摘要和篇幅。`;

const initialTitle = props.brief.title;
const initialBody = buildGeneratedBody(
  initialTitle,
  primaryKeyword.value,
  props.brief.retest_questions[0] ?? "咨询前需要确认哪些信息？",
);
const initialArticles: ArticleItem[] = [
  {
    id: "article-service",
    title: initialTitle,
    contentType: "服务说明",
    primaryKeyword: primaryKeyword.value,
    updatedAt: "11:42",
    status: "needs_facts",
    qualityScore: 82,
    version: 2,
    body: initialBody,
  },
  {
    id: "article-selection",
    title: `${primaryKeyword.value}培训怎么选？先看这 5 个信息`,
    contentType: "选择指南",
    primaryKeyword: `${primaryKeyword.value}怎么选`,
    updatedAt: "10:18",
    status: "ready",
    qualityScore: 91,
    version: 1,
    body: buildGeneratedBody(
      `${primaryKeyword.value}培训怎么选？先看这 5 个信息`,
      `${primaryKeyword.value}怎么选`,
      "选择少儿美术培训机构时应该看什么？",
    ),
  },
  {
    id: "article-faq",
    title: `了解${props.clientName}前常问的 8 个问题`,
    contentType: "问答文章",
    primaryKeyword: secondaryKeyword.value,
    updatedAt: "昨天",
    status: "ready",
    qualityScore: 89,
    version: 1,
    body: buildGeneratedBody(
      `了解${props.clientName}前常问的 8 个问题`,
      secondaryKeyword.value,
      `${props.clientName}提供哪些服务？`,
    ),
  },
];
const initialArticle = initialArticles[0]!;

const articles = ref<ArticleItem[]>(initialArticles);
const selectedArticleId = ref(initialArticle.id);
const editorBody = ref(initialArticle.body);
const savedBody = ref(editorBody.value);
const savedMessage = ref("");
const versionPending = ref(false);
const isGenerating = ref(false);
let generationTimer: number | undefined;

const selectedArticle = computed(
  () =>
    articles.value.find((article) => article.id === selectedArticleId.value) ??
    initialArticle,
);
const qualityBlocked = computed(
  () => selectedArticle.value.status === "needs_facts",
);
const hasUnsavedChanges = computed(() => editorBody.value !== savedBody.value);
const articleStatusLabel: Record<ArticleStatus, string> = {
  ready: "AI 已生成",
  needs_facts: "待补事实",
};
const qualityDimensions = computed(
  () =>
    [
      [
        "事实一致性",
        qualityBlocked.value ? "阻断" : "通过",
        qualityBlocked.value
          ? "服务范围仍是待确认信息，AI 已避免写成事实。"
          : "事实边界清晰，未把待确认信息写成既定事实。",
      ],
      ["问题相关性", "通过", "正文直接回答目标用户问题。"],
      ["实体清晰度", "通过", "企业名称、地区意图与服务关系清晰。"],
      [
        "可摘取回答",
        qualityBlocked.value ? "待改进" : "通过",
        qualityBlocked.value
          ? "需补充服务范围答案段。"
          : "摘要、列表和 FAQ 可独立理解。",
      ],
      ["来源可追溯", "通过", "仅关联已授权企业资料。"],
      ["自然表达", "通过", "未使用绝对化承诺或机械套话。"],
      ["渠道适配", "通过", "已形成可继续适配渠道的基础版本。"],
      ["合规", "通过", "未使用未授权素材。"],
    ] as const,
);

const selectArticle = (article: ArticleItem): void => {
  selectedArticleId.value = article.id;
  editorBody.value = article.body;
  savedBody.value = article.body;
  savedMessage.value = "";
  versionPending.value = false;
};
const saveChanges = (): void => {
  const current = selectedArticle.value;
  articles.value = articles.value.map((article) =>
    article.id === current.id
      ? {
          ...article,
          body: editorBody.value,
          updatedAt: "刚刚",
          version: article.version + 1,
        }
      : article,
  );
  savedBody.value = editorBody.value;
  savedMessage.value = "修改已保存为独立版本，AI 原始版本仍可追溯。";
};
const keepCurrent = (): void => {
  versionPending.value = false;
};
const applyVersion = (): void => {
  editorBody.value +=
    "\n\n## 咨询前可确认的信息\n\n建议直接确认服务范围、适合人群和当前可提供的具体安排，并以机构最新公开信息为准。";
  versionPending.value = false;
  savedMessage.value = "";
};
const generateArticle = (): void => {
  if (isGenerating.value) return;
  isGenerating.value = true;
  savedMessage.value = "";
  generationTimer = window.setTimeout(() => {
    const generatedTitle = `${primaryKeyword.value}咨询前需要确认哪些信息？`;
    const generatedArticle: ArticleItem = {
      id: `article-${Date.now()}`,
      title: generatedTitle,
      contentType: "咨询指南",
      primaryKeyword: primaryKeyword.value,
      updatedAt: "刚刚",
      status: "ready",
      qualityScore: 90,
      version: 1,
      body: buildGeneratedBody(
        generatedTitle,
        primaryKeyword.value,
        "咨询本地少儿美术服务前应该确认什么？",
      ),
    };
    articles.value = [generatedArticle, ...articles.value];
    selectArticle(generatedArticle);
    isGenerating.value = false;
    generationTimer = undefined;
  }, 700);
};
const goToFacts = (): void => {
  void router.push({ name: "knowledge", query: { clientId: props.clientId } });
};
onUnmounted(() => {
  if (generationTimer !== undefined) window.clearTimeout(generationTimer);
});
</script>

<template>
  <section class="mock-workbench">
    <header class="content-production-header">
      <div>
        <strong>AI 文章生产</strong>
        <span>AI 先写完整初稿，生成完成后才开放编辑。</span>
      </div>
      <button
        class="button primary"
        :disabled="isGenerating"
        @click="generateArticle"
      >
        {{ isGenerating ? "生成中…" : "AI 生成新文章" }}
      </button>
    </header>

    <section class="generation-context" aria-label="AI 生成依据">
      <div><strong>企业事实 2 条</strong><span>名称、核心服务</span></div>
      <div>
        <strong>目标关键词 {{ brief.target_keywords.length }} 个</strong
        ><span>{{ brief.target_keywords.join("、") }}</span>
      </div>
      <div>
        <strong>GEO 建议 4 项</strong><span>实体、直答、列表、FAQ</span>
      </div>
      <div>
        <strong>适配渠道 {{ recommendedChannels.length }} 个</strong
        ><span>{{ recommendedChannels.join("、") }}</span>
      </div>
    </section>

    <section v-if="isGenerating" class="generation-progress" role="status">
      <span class="generation-spinner" aria-hidden="true" />
      <div>
        <strong>AI 正在生成文章</strong>
        <small>正在组合企业资料、关键词、用户问题、GEO 结构和渠道要求…</small>
      </div>
    </section>

    <section class="content-production-layout">
      <aside class="panel article-list-panel">
        <header class="panel-header">
          <h2>文章列表</h2>
          <span>{{ articles.length }} 篇</span>
        </header>
        <div class="article-list">
          <button
            v-for="article in articles"
            :key="article.id"
            class="article-list-item"
            :class="{ selected: selectedArticleId === article.id }"
            type="button"
            :aria-label="`打开文章：${article.title}`"
            :aria-pressed="selectedArticleId === article.id"
            @click="selectArticle(article)"
          >
            <span class="article-list-topline"
              ><small>{{ article.contentType }}</small
              ><span class="article-status" :data-status="article.status">{{
                articleStatusLabel[article.status]
              }}</span></span
            >
            <strong>{{ article.title }}</strong>
            <span class="article-keyword">{{ article.primaryKeyword }}</span>
            <span class="article-list-meta"
              >{{ article.updatedAt }} · v{{ article.version }} · 质量
              {{ article.qualityScore }}</span
            >
          </button>
        </div>
      </aside>

      <article class="panel editor-panel">
        <header class="panel-header editor-titlebar">
          <div>
            <h2>{{ selectedArticle.title }}</h2>
            <span
              >AI 生成 · v{{ selectedArticle.version }} ·
              {{ selectedArticle.primaryKeyword }}</span
            >
          </div>
          <span v-if="hasUnsavedChanges" class="edit-state">有未保存修改</span>
        </header>
        <textarea
          v-model="editorBody"
          aria-label="内容正文"
          class="content-editor"
        />
        <footer class="editor-actions">
          <button
            class="button"
            :disabled="!hasUnsavedChanges"
            @click="saveChanges"
          >
            保存修改</button
          ><button class="button primary" @click="versionPending = true">
            AI 再优化
          </button>
          <button class="button" :disabled="qualityBlocked">导出内容</button>
        </footer>
      </article>

      <aside class="content-side">
        <section class="panel source-panel">
          <header class="panel-header">
            <h2>本篇生成依据</h2>
            <span>仅限已授权资料</span>
          </header>
          <div class="generation-brief">
            <small>目标用户问题</small>
            <strong>{{
              brief.retest_questions[0] ?? "咨询前需要确认哪些信息？"
            }}</strong>
            <small>内容角度</small>
            <p>{{ brief.angle }}</p>
            <small>关键词</small>
            <div class="keyword-chips">
              <span v-for="keyword in brief.target_keywords" :key="keyword">{{
                keyword
              }}</span>
            </div>
            <small>优化结构</small>
            <p>开头直答 · 实体关系 · 选择清单 · FAQ · 信息来源说明</p>
          </div>
        </section>
        <section class="panel quality-panel">
          <header class="panel-header">
            <h2>质量检查</h2>
            <span :class="qualityBlocked ? 'risk-badge' : 'level-badge'">{{
              qualityBlocked ? "阻断" : "可导出"
            }}</span>
          </header>
          <p v-if="qualityBlocked">
            服务范围仍未确认；AI 已避免把推断写成事实，当前暂不导出。
          </p>
          <p v-else>事实边界与来源检查已通过，当前版本可以导出。</p>
          <ul class="compact-list quality-list">
            <li v-for="[name, status, note] in qualityDimensions" :key="name">
              <div>
                <strong>{{ name }}</strong
                ><small>{{ note }}</small>
              </div>
              <span :class="status === '阻断' ? 'risk-badge' : 'level-badge'">{{
                status
              }}</span>
            </li>
          </ul>
          <button class="button" @click="goToFacts">查看待补齐事实</button>
        </section>
      </aside>
    </section>

    <section v-if="versionPending" class="panel version-panel">
      <h2>优化版本待确认</h2>
      <p>AI 建议新增一段直接回答，不会覆盖当前已编辑正文。</p>
      <button class="button primary" @click="applyVersion">采用为新版本</button
      ><button class="button" @click="keepCurrent">保留当前版本</button>
    </section>
    <p v-if="savedMessage" class="state-success" role="status">
      {{ savedMessage }}
    </p>
    <p class="content-outcome-note">
      目标是提高公开内容被平台理解、检索和引用的机会；不承诺任何平台一定收录、推荐或给出特定排名。
    </p>
  </section>
</template>
