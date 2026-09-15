import { callBackend, forwardBackend, safeProxyError } from "@/lib/backend";

export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  try {
    const response = await callBackend("/health/ready", {}, false);
    return forwardBackend(response);
  } catch {
    return safeProxyError();
  }
}
