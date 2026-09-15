import "server-only";

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";

function backendUrl(path: string): string {
  const base = (
    process.env.RAGEVAL_API_URL ??
    process.env.RAGEVAL_BACKEND_URL ??
    DEFAULT_BACKEND_URL
  ).replace(/\/+$/, "");
  return `${base}${path}`;
}

function apiKey(): string {
  const value = process.env.RAGEVAL_API_KEY ?? process.env.RAGEVAL_SERVING_API_KEY;
  if (!value) {
    throw new Error("RAG-Eval API key is not configured");
  }
  return value;
}

export async function callBackend(
  path: string,
  init: RequestInit = {},
  authenticated = true,
): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("accept", "application/json");
  if (init.body) {
    headers.set("content-type", "application/json");
  }
  if (authenticated) {
    headers.set("x-api-key", apiKey());
  }

  return fetch(backendUrl(path), {
    ...init,
    headers,
    cache: "no-store",
    signal: AbortSignal.timeout(60_000),
  });
}

export async function forwardBackend(response: Response): Promise<Response> {
  const body = await response.text();
  const headers = new Headers();
  headers.set(
    "content-type",
    response.headers.get("content-type") ?? "application/json",
  );
  const requestId = response.headers.get("x-request-id");
  if (requestId) {
    headers.set("x-request-id", requestId);
  }
  return new Response(body, {
    status: response.status,
    headers,
  });
}

export function safeProxyError(): Response {
  return Response.json(
    {
      code: "frontend_proxy_error",
      message: "The RAG-Eval backend could not be reached.",
    },
    { status: 502 },
  );
}
