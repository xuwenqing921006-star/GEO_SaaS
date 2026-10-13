export type ArticleCoverStyle = "azure" | "sunrise" | "mint";
export const ARTICLE_COVER_RENDER_VERSION = "v4-photo";

export interface ArticleCoverStyleOption {
  value: ArticleCoverStyle;
  label: string;
  description: string;
}

export const ARTICLE_COVER_STYLES: readonly ArticleCoverStyleOption[] = [
  {
    value: "azure",
    label: "智慧蓝",
    description: "清晰专业，适合知识与教育内容",
  },
  {
    value: "sunrise",
    label: "暖阳橙",
    description: "温暖亲和，适合家庭与生活服务",
  },
  {
    value: "mint",
    label: "清新青",
    description: "轻盈自然，适合健康与成长主题",
  },
];

export const articleCoverUrl = (
  documentId: string,
  versionId: string,
  style: ArticleCoverStyle,
  download: boolean,
  imageMaterialIds: string[] = [],
): string => {
  const query = new URLSearchParams({
    style,
    render: ARTICLE_COVER_RENDER_VERSION,
  });
  if (imageMaterialIds.length) query.set("images", imageMaterialIds.join(","));
  if (download) query.set("download", "true");
  return `/api/v1/documents/${encodeURIComponent(documentId)}/versions/${encodeURIComponent(versionId)}/cover?${query}`;
};
