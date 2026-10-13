import type { DiagnosticChannelSignal } from "./api/dto";

export interface DiagnosticChannelAction {
  channelId: "baijia" | "sohu" | "netease" | "toutiao" | "penguin";
  channelName: string;
  title: string;
  description: string;
  action: string;
  basis: "observed";
}

const CHANNEL_CATALOG: readonly Omit<
  DiagnosticChannelAction,
  "title" | "description" | "basis"
>[] = [
  {
    channelId: "baijia",
    channelName: "百家号",
    action: "先发布地区服务说明、选择指南和常见问题，每篇只解决一个真实问题。",
  },
  {
    channelId: "sohu",
    channelName: "搜狐号",
    action: "优先发布知识科普、经验教程和场景文章，减少直接营销表达。",
  },
  {
    channelId: "netease",
    channelName: "网易号",
    action: "发布行业知识、案例复盘和服务流程，保持企业名称与知识库一致。",
  },
  {
    channelId: "toutiao",
    channelName: "头条号",
    action: "只发布有实际信息增量的本地指南，避免批量同质稿和关键词堆砌。",
  },
  {
    channelId: "penguin",
    channelName: "企鹅号",
    action: "发布知识科普、经验方法和本地观察，使用真实配图并如实声明AI生成。",
  },
];

const normalizedChannelId = (
  channelId: string,
): DiagnosticChannelAction["channelId"] | null => {
  if (channelId === "baidu") return "baijia";
  return CHANNEL_CATALOG.some((channel) => channel.channelId === channelId)
    ? (channelId as DiagnosticChannelAction["channelId"])
    : null;
};

export const buildChannelActionPlan = (
  signals: readonly DiagnosticChannelSignal[],
  limit = 3,
): DiagnosticChannelAction[] => {
  const result: DiagnosticChannelAction[] = [];
  const used = new Set<DiagnosticChannelAction["channelId"]>();
  const sortedSignals = [...signals].sort(
    (left, right) => right.signal_score - left.signal_score,
  );

  for (const signal of sortedSignals) {
    const channelId = normalizedChannelId(signal.channel_id);
    if (!channelId || used.has(channelId)) continue;
    const channel = CHANNEL_CATALOG.find(
      (candidate) => candidate.channelId === channelId,
    )!;
    result.push({
      ...channel,
      title: `优先注册或连接${channel.channelName}`,
      description: `本次诊断在 AI 回答来源中观察到 ${signal.source_count} 条来自${channel.channelName}的内容，可优先测试该渠道。`,
      basis: "observed",
    });
    used.add(channelId);
    if (result.length >= limit) return result;
  }

  return result;
};
