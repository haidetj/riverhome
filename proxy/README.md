# RiverHome API proxy

A tiny [Cloudflare Worker](https://workers.cloudflare.com/) that keeps your
Anthropic API key **off the public web app**. The browser calls this Worker;
the Worker attaches the secret key and forwards the request to Anthropic.

The key lives only in Cloudflare (as an encrypted secret) — it is never
committed to this repo and never sent to a phone.

## One-time setup (~5 minutes, free tier is plenty)

1. **Install Wrangler** (Cloudflare's CLI) and log in:
   ```bash
   npm install -g wrangler
   wrangler login
   ```

2. **From this `proxy/` folder, add your secrets:**
   ```bash
   cd proxy
   wrangler secret put ANTHROPIC_API_KEY     # paste your sk-ant-... key
   wrangler secret put GATE_PASSWORD         # type: trail  (must match CONFIG.password)
   ```

3. **Deploy:**
   ```bash
   wrangler deploy
   ```
   Wrangler prints a URL like:
   ```
   https://riverhome-proxy.<your-subdomain>.workers.dev
   ```

4. **Point the app at it.** In `../index.html`, set `proxyUrl` in the `CONFIG`
   block to that URL, then commit and push:
   ```js
   proxyUrl: "https://riverhome-proxy.<your-subdomain>.workers.dev",
   ```

That's it. The magazine "read" will start coming from Claude again, and the
key stays private.

## Notes

- `ALLOWED_ORIGIN` in `wrangler.toml` restricts who can call the Worker to your
  Pages site (`https://haidetj.github.io`). If your Pages URL is different,
  change it and re-run `wrangler deploy`.
- To **rotate the key** later: `wrangler secret put ANTHROPIC_API_KEY` again and
  redeploy — no app change needed.
- To change the password, update both `wrangler secret put GATE_PASSWORD` and
  `CONFIG.password` in `index.html`.
- The Worker only forwards to Anthropic's Messages API; it does nothing else.
