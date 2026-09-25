# RCA Atlas Worker

This Cloudflare Worker is the public boundary for RCA Atlas. It accepts a
question from `https://coszo.org`, requests bounded evidence from the private
Graph-RAG API, and sends that evidence package to Gemini for synthesis.

It never exposes the Gemini or Graph-RAG API credentials to the browser.

## Deployment

Authenticate on the VM with `npx wrangler login --device`, then from this
directory run `npm run check` followed by `npx wrangler deploy`.

Set these Worker secrets after deployment (values are prompted, never commit
them):

```bash
npx wrangler secret put GEMINI_API_KEY
npx wrangler secret put ATLAS_API_KEY
npx wrangler secret put ATLAS_API_ORIGIN
```

`ATLAS_API_ORIGIN` is an HTTPS Cloudflare Tunnel URL terminating at the
loopback-only Graph-RAG API. `ATLAS_API_KEY` is the matching private API key.
Configure a Cloudflare rate-limit rule for `POST /v1/answer` before enabling
the UI endpoint in production.

## Test

`npm test` runs the `node --test` unit tests (no dependencies): the hypo71 event parser, hit excerpts, and the
numbered-citation prompt.
