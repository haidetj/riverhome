// RiverHome API proxy — a tiny Cloudflare Worker that holds the Anthropic API
// key server-side, so the key NEVER ships inside the public web app.
//
// The browser calls this Worker; the Worker adds the secret key and forwards
// the request to Anthropic. Everything else about the request is unchanged.
//
// Secrets (set once with `wrangler secret put NAME`):
//   ANTHROPIC_API_KEY  — your Anthropic key (sk-ant-...). Never committed.
//   GATE_PASSWORD      — shared password the app must send. Set it to the same
//                        value as CONFIG.password in index.html ("trail").
//
// Vars (in wrangler.toml, safe to commit):
//   ALLOWED_ORIGIN     — the exact site allowed to call this Worker,
//                        e.g. https://haidetj.github.io  (use "*" to allow any).

const ANTHROPIC_URL = "https://api.anthropic.com/v1/messages";

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const allowed = env.ALLOWED_ORIGIN || "*";
    const cors = {
      "Access-Control-Allow-Origin": allowed,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "content-type, x-riverhome-pass",
      "Access-Control-Max-Age": "86400",
      "Vary": "Origin"
    };

    // CORS preflight
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (request.method !== "POST") return json({ error: "Method not allowed" }, 405, cors);

    // Only accept calls from the app's own origin (when one is configured).
    if (allowed !== "*" && origin && origin !== allowed)
      return json({ error: "Forbidden origin" }, 403, cors);

    // Shared-password gate — a courtesy lock so a stray script can't burn tokens.
    if (env.GATE_PASSWORD && request.headers.get("x-riverhome-pass") !== env.GATE_PASSWORD)
      return json({ error: "Unauthorized" }, 401, cors);

    if (!env.ANTHROPIC_API_KEY)
      return json({ error: "Proxy missing ANTHROPIC_API_KEY secret" }, 500, cors);

    let payload;
    try { payload = await request.json(); } catch { return json({ error: "Bad JSON body" }, 400, cors); }

    const upstream = await fetch(ANTHROPIC_URL, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": env.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01"
      },
      body: JSON.stringify(payload)
    });

    // Pass Anthropic's response straight back (status + body), with CORS headers.
    const body = await upstream.text();
    return new Response(body, {
      status: upstream.status,
      headers: { ...cors, "content-type": "application/json" }
    });
  }
};

function json(obj, status, cors) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { ...cors, "content-type": "application/json" }
  });
}
