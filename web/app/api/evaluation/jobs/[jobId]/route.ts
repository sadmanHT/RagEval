import { callBackend, forwardBackend, safeProxyError } from "@/lib/backend";

export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ jobId: string }>;
};

export async function GET(
  _request: Request,
  context: RouteContext,
): Promise<Response> {
  try {
    const { jobId } = await context.params;
    const response = await callBackend(
      `/eval/jobs/${encodeURIComponent(jobId)}`,
    );
    return forwardBackend(response);
  } catch {
    return safeProxyError();
  }
}
