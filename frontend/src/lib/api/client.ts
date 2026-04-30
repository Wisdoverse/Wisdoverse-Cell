const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "/api/v1";

class ApiClientError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiClientError";
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${path}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);

  try {
    const res = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
      credentials: "include",
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText || `HTTP ${res.status}` }));
      throw new ApiClientError(res.status, body.detail || res.statusText || `HTTP ${res.status}`);
    }

    return res.json().catch(() => {
      throw new ApiClientError(res.status, `Invalid JSON response from ${path}`);
    });
  } catch (err) {
    if (err instanceof ApiClientError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiClientError(408, `Request timeout: ${path}`);
    }
    console.error(`[api-client] Network error on ${path}:`, err);
    throw err;
  } finally {
    clearTimeout(timeout);
  }
}

// Retry wrapper for GET requests
async function requestWithRetry<T>(
  path: string,
  options: RequestInit = {},
  retries = 3,
): Promise<T> {
  for (let i = 0; i < retries; i++) {
    try {
      return await request<T>(path, options);
    } catch (err) {
      if (i === retries - 1) throw err;
      if (err instanceof ApiClientError && err.status < 500 && err.status !== 408) throw err;
      console.warn(`[api-client] Retry ${i + 1}/${retries} for ${path}:`, err);
      await new Promise((r) => setTimeout(r, 1000 * Math.pow(2, i)));
    }
  }
  throw new Error("Unreachable");
}

function buildQuery(params: object): string {
  const entries = Object.entries(params).filter(([, v]) => v != null && v !== "");
  if (entries.length === 0) return "";
  return (
    "?" +
    new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString()
  );
}

export const apiClient = {
  get: <T>(path: string, params?: object) =>
    requestWithRetry<T>(path + buildQuery(params || {})),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    }),
  delete: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "DELETE",
      body: body ? JSON.stringify(body) : undefined,
    }),
};

export { ApiClientError };
