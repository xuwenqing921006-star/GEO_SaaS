import type {
  ContactPolicy,
  PromptCategory,
  PromptTemplateData,
  PromptTemplateListData,
  PromptTemplateVersionData,
} from "./dto";
import { apiRequest } from "./http";

export const getPromptTemplates = (
  category?: PromptCategory,
): Promise<PromptTemplateListData> => {
  const query = category
    ? `?${new URLSearchParams({ category }).toString()}`
    : "";
  return apiRequest(`/api/v1/prompt-templates${query}`);
};

export const updatePromptTemplate = (
  templateId: string,
  input: {
    version: number;
    template_text: string;
    active: boolean;
    contact_policy?: ContactPolicy | null;
    change_note: string;
  },
): Promise<PromptTemplateData> =>
  apiRequest(`/api/v1/prompt-templates/${encodeURIComponent(templateId)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });

export const restorePromptTemplate = (
  templateId: string,
  version: number,
): Promise<PromptTemplateData> =>
  apiRequest(
    `/api/v1/prompt-templates/${encodeURIComponent(templateId)}/restore`,
    {
      method: "POST",
      body: JSON.stringify({ version }),
    },
  );

export const getPromptTemplateVersions = (
  templateId: string,
): Promise<{ items: PromptTemplateVersionData[] }> =>
  apiRequest(
    `/api/v1/prompt-templates/${encodeURIComponent(templateId)}/versions`,
  );
