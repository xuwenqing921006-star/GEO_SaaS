import { apiRequest } from "./http";
import type {
  ClientFilters,
  ClientDetail,
  ClientStatus,
  ClientsPage,
  CreateClientInput,
  DashboardData,
} from "./dto";

export const listClients = (filters: ClientFilters): Promise<ClientsPage> => {
  const params = new URLSearchParams({
    page: String(filters.page),
    page_size: String(filters.page_size),
    sort: filters.sort,
  });
  if (filters.q) params.set("q", filters.q);
  if (filters.status) params.set("status", filters.status);
  return apiRequest(`/api/v1/clients?${params.toString()}`);
};
export const getDashboard = (clientId: string): Promise<DashboardData> =>
  apiRequest(`/api/v1/clients/${clientId}/dashboard`);
export const getClient = (clientId: string): Promise<ClientDetail> =>
  apiRequest(`/api/v1/clients/${encodeURIComponent(clientId)}`);
export const createClient = (input: CreateClientInput): Promise<ClientDetail> =>
  apiRequest("/api/v1/clients", {
    method: "POST",
    body: JSON.stringify(input),
  });
export const updateClientName = (
  clientId: string,
  version: number,
  standard_name: string,
): Promise<ClientDetail> =>
  apiRequest(`/api/v1/clients/${clientId}`, {
    method: "PATCH",
    body: JSON.stringify({ version, standard_name }),
  });
export const updateClient = (
  clientId: string,
  version: number,
  input: CreateClientInput,
): Promise<ClientDetail> =>
  apiRequest(`/api/v1/clients/${clientId}`, {
    method: "PATCH",
    body: JSON.stringify({ version, ...input }),
  });
export const updateClientStatus = (
  clientId: string,
  version: number,
  status: Extract<ClientStatus, "active" | "paused">,
): Promise<ClientDetail> =>
  apiRequest(`/api/v1/clients/${clientId}`, {
    method: "PATCH",
    body: JSON.stringify({ version, status }),
  });
export const archiveClient = (
  clientId: string,
  version: number,
  reason: string,
): Promise<ClientDetail> =>
  apiRequest(`/api/v1/clients/${clientId}/archive`, {
    method: "POST",
    body: JSON.stringify({ version, reason }),
  });
export const restoreClient = (
  clientId: string,
  version: number,
): Promise<ClientDetail> =>
  apiRequest(`/api/v1/clients/${clientId}/restore`, {
    method: "POST",
    body: JSON.stringify({ version }),
  });
