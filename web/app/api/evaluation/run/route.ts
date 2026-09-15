import { callBackend, forwardBackend, safeProxyError } from "@/lib/backend";

export const runtime = "nodejs";

export async function POST(request: Request): Promise<Response> {
  try {
    const body = await request.text();
    const response = await callBackend("/eval/run", {
      method: "POST",
      body,
    });
    return forwardBackend(response);
  } catch {
    return safeProxyError();
  }
}
