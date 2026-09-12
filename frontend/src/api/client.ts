const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
export const API_BASE_URL = configuredBaseUrl || "/api";

const UNSAFE_DETAIL = /(traceback|sqlalchemy|postgres|password|api[_ -]?key|[a-z]:\\|\/users\/|\/home\/)/i;

export class ApiError extends Error {
  readonly status: number;
  readonly transportUncertain: boolean;

  constructor(message: string, status = 0, transportUncertain = false) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.transportUncertain = transportUncertain;
  }
}

function safeDetail(value: unknown): string | null {
  if (typeof value !== "string" || value.length === 0 || value.length > 240) return null;
  return UNSAFE_DETAIL.test(value) ? null : value;
}

function statusMessage(status: number, detail: string | null): string {
  if (status === 404) return "The requested machine or report was not found.";
  if (status === 409) {
    if (detail?.toLowerCase().includes("processing")) {
      return "An identical maintenance request is already processing. Try again shortly.";
    }
    return "This request conflicts with an earlier idempotent request.";
  }
  if (status === 400 || status === 422) return "The submitted input is not valid.";
  if (status === 503) return "Required analysis infrastructure is unavailable.";
  if (status >= 500) return "The server could not safely complete this request.";
  return detail ?? "The requested data could not be loaded.";
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(
      "SentinelAI backend is unavailable. Check the local service and retry.",
      0,
      true,
    );
  }

  if (!response.ok) {
    let detail: string | null = null;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      detail = safeDetail(payload.detail);
    } catch {
      detail = null;
    }
    throw new ApiError(statusMessage(response.status, detail), response.status);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError("SentinelAI returned an invalid response. Retry the request.");
  }
}

