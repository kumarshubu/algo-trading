import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

async function proxy(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  const { path } = await params;
  const { search } = new URL(request.url);
  const target = `${BACKEND}/api/v1/${path.join("/")}${search}`;

  const headers = new Headers();
  request.headers.forEach((v, k) => {
    if (!["host", "connection"].includes(k)) headers.set(k, v);
  });

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const body = hasBody ? await request.arrayBuffer() : undefined;

  const upstream = await fetch(target, {
    method: request.method,
    headers,
    body: body ? Buffer.from(body) : undefined,
  });

  const resHeaders = new Headers();
  upstream.headers.forEach((v, k) => {
    if (k !== "transfer-encoding") resHeaders.set(k, v);
  });

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: resHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
