/**
 * Freebuff Sites entry point for Study Companion.
 *
 * The application itself is a FastAPI service that cannot run on Workers, so
 * this Worker does two things:
 *
 *   1. Serves the static frontend (index shell, admin dashboard, assets) from
 *      the bundled `backend/static` directory.
 *   2. Proxies the same-origin API paths the frontend calls (`/admin`, `/auth`,
 *      `/api`, ...) to the deployed FastAPI service, so the preview exercises
 *      the real API instead of returning 404s.
 *
 * Auth is unchanged: the backend still enforces the admin key and session
 * cookies, which are set for the preview origin because the browser talks to
 * this Worker only.
 */

const UPSTREAM_ORIGIN = "https://study-companion-o7k3.onrender.com";

/** Bumped when the frontend changes; mirrors the backend's asset versioning. */
const ASSET_VERSION = "20261116a";

const API_PREFIXES = [
  "/admin",
  "/api",
  "/auth",
  "/billing",
  "/chat",
  "/documents",
  "/tasks",
  "/progress",
  "/toolbox",
  "/assessment",
  "/feedback",
  "/health",
];

function isApiPath(pathname) {
  return API_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

async function serveAsset(env, request, file, headers = {}) {
  const url = new URL(request.url);
  const response = await env.ASSETS.fetch(
    new URL(file, url.origin).toString(),
    { method: "GET" },
  );
  if (!response.ok) return response;

  const out = new Response(response.body, response);
  for (const [name, value] of Object.entries(headers)) {
    out.headers.set(name, value);
  }
  out.headers.delete("content-length");
  return out;
}

/** The shell is rendered per request in production, so expand it here too. */
async function serveShell(env, request) {
  const response = await serveAsset(env, request, "/index.html", {
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store",
  });
  if (!response.ok) return response;

  const html = (await response.text()).replaceAll(
    "__ASSET_VERSION__",
    ASSET_VERSION,
  );
  const headers = new Headers(response.headers);
  headers.delete("content-length");
  return new Response(html, { status: response.status, headers });
}

async function proxyToUpstream(request, url) {
  const upstream = new URL(url.pathname + url.search, UPSTREAM_ORIGIN);
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.set("X-Forwarded-Host", url.host);
  headers.set("X-Forwarded-Proto", url.protocol.replace(":", ""));

  const init = { method: request.method, headers, redirect: "manual" };
  if (request.method !== "GET" && request.method !== "HEAD") {
    // Buffer the body: some runtimes cannot stream a request body upstream.
    init.body = await request.arrayBuffer();
  }

  let response;
  try {
    response = await fetch(upstream.toString(), init);
  } catch (error) {
    console.error("upstream request failed", url.pathname, error);
    return Response.json(
      { detail: "Upstream API request failed." },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }

  const outHeaders = new Headers(response.headers);
  // Keep redirects on the preview origin instead of leaking the upstream host.
  const location = outHeaders.get("location");
  if (location) {
    const target = new URL(location, UPSTREAM_ORIGIN);
    if (target.origin === UPSTREAM_ORIGIN) {
      outHeaders.set("location", target.pathname + target.search);
    }
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: outHeaders,
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (isApiPath(path)) {
      return proxyToUpstream(request, url);
    }

    if (path === "/" || path === "/index.html") {
      return serveShell(env, request);
    }

    if (path === "/admin") {
      return serveAsset(env, request, "/admin.html", {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
      });
    }

    if (path === "/favicon.ico") {
      return serveAsset(env, request, "/favicon.svg", {
        "Content-Type": "image/svg+xml",
      });
    }

    if (path === "/manifest.webmanifest") {
      return serveAsset(env, request, "/manifest.webmanifest", {
        "Content-Type": "application/manifest+json",
      });
    }

    if (path === "/sw.js") {
      return serveAsset(env, request, "/sw.js", {
        "Content-Type": "application/javascript",
        "Service-Worker-Allowed": "/",
      });
    }

    // Production mounts the same files under /static, so mirror that here.
    if (path.startsWith("/static/")) {
      return serveAsset(env, request, path.slice("/static".length));
    }

    return env.ASSETS.fetch(request);
  },
};
