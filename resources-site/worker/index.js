/* Student Resources Centre worker.
 *
 * Serves the page (./page.js) and the content it fetches from /api/resources/*,
 * which lives in ./data.js so the JSON never has to be public. Adding a section
 * means adding it to resources-site/data/ and regenerating data.js and page.js -
 * see README.md.
 */

import { careerPathResponse } from "./career-path.js";
import { library, resources } from "./data.js";
import { pageHtml } from "./page.js";

const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "public, max-age=300",
};

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    // The centre has always lived at /resources; keep that as the entry point.
    if (path === "/") {
      return Response.redirect(new URL("/resources", url.origin).toString(), 307);
    }

    // Served from a module, not from the assets directory: the assets layer
    // rewrites "/resources.html" to "/resources", which would loop right back here.
    if (path === "/resources" || path === "/resources/" || path === "/resources.html") {
      return new Response(pageHtml, {
        headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-cache, must-revalidate" },
      });
    }

    if (path === "/health") return json({ status: "ok", app: "student-resources-centre" });

    // Computed rather than stored: the page sends a field, regions and a band.
    if (path === "/api/resources/career-path") {
      const payload = careerPathResponse(url.searchParams);
      return payload ? json(payload) : json({ error: "Unknown field, region or performance band" }, 400);
    }

    const section = path.match(/^\/api\/resources\/([a-z-]+)$/);
    if (section) {
      const data = resources[section[1]];
      return data ? json(data) : json({ error: "Unknown resource section" }, 404);
    }

    const document = path.match(/^\/api\/resources\/library\/([a-z0-9-]+)$/);
    if (document) {
      const entry = library[document[1]];
      if (!entry) return json({ error: "Unknown document" }, 404);
      const meta = resources.library.documents.find((item) => item.slug === document[1]);
      return json({ document: meta, content: entry.content });
    }

    const download = path.match(/^\/api\/resources\/library\/([a-z0-9-]+)\/download$/);
    if (download) {
      const document = library[download[1]];
      if (!document) return json({ error: "Unknown document" }, 404);
      return new Response(document.content, {
        headers: {
          "content-type": "text/markdown; charset=utf-8",
          "content-disposition": `attachment; filename="${document.file}"`,
          "cache-control": "public, max-age=600",
        },
      });
    }

    if (path.startsWith("/api/")) return json({ error: "Not found" }, 404);

    return env.ASSETS.fetch(request);
  },
};
