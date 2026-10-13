import type { ApiErrorBody, ApiSuccess } from "./dto";

let csrfToken: string | null = null;
export const shouldUseMock = (
  environment: Record<string, string | undefined>,
): boolean => environment.VITE_USE_MOCK === "true";

export class ApiError extends Error {
  readonly status: number;
  readonly fieldErrors: { field: string; message: string }[];
  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.status = status;
    this.fieldErrors = body.data.field_errors;
  }
}
export const setCsrfToken = (token: string | null): void => {
  csrfToken = token;
};
export const apiRequest = async <T>(
  path: string,
  init: RequestInit = {},
): Promise<T> => {
  const method = init.method ?? "GET";
  const headers = new Headers(init.headers);
  if (
    init.body &&
    !(typeof FormData !== "undefined" && init.body instanceof FormData)
  )
    headers.set("Content-Type", "application/json");
  if (["POST", "PATCH", "PUT", "DELETE"].includes(method) && csrfToken)
    headers.set("X-CSRF-Token", csrfToken);
  const request = {
    ...init,
    method,
    headers,
    credentials: "include" as RequestCredentials,
  };
  const response =
    import.meta.env.DEV && import.meta.env.VITE_USE_MOCK === "true"
      ? await (await import("./mock")).mockRequest(path, request)
      : await fetch(path, request);
  const body = (await response.json()) as ApiSuccess<T> | ApiErrorBody;
  if (!response.ok) {
    const error = new ApiError(response.status, body as ApiErrorBody);
    if (response.status === 401)
      window.dispatchEvent(
        new CustomEvent("geo:unauthorized", { detail: error }),
      );
    throw error;
  }
  return (body as ApiSuccess<T>).data;
};
