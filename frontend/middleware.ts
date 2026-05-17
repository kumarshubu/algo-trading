import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  const apiKey = process.env.BACKEND_API_KEY;

  // Only intercept API backend requests
  if (request.nextUrl.pathname.startsWith("/api/backend/")) {
    const requestHeaders = new Headers(request.headers);
    if (apiKey) {
      requestHeaders.set("X-API-Key", apiKey);
    }
    return NextResponse.next({
      request: {
        headers: requestHeaders,
      },
    });
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/api/backend/:path*"],
};
