import { apiRequest } from "./http";
import type { SessionData } from "./dto";

export const getSession = (): Promise<SessionData> =>
  apiRequest("/api/v1/auth/session");
export const login = (
  username: string,
  password: string,
): Promise<SessionData> =>
  apiRequest("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
export const logout = (): Promise<{ logged_out: boolean }> =>
  apiRequest("/api/v1/auth/session", { method: "DELETE" });
export const changePassword = (
  current_password: string,
  new_password: string,
): Promise<{ changed: boolean; relogin_required: boolean }> =>
  apiRequest("/api/v1/auth/password", {
    method: "PUT",
    body: JSON.stringify({ current_password, new_password }),
  });
