// Runs the Worker's answer path locally against a Graph-RAG API and records the prompt it would send the model,
// with the model call stubbed: the evidence a question gets, without asking a model. evidence_ab.py compares two
// APIs (two searches) this way.
// Usage: ATLAS_API_KEY=... node evidence_prompts.mjs <api origin> <questions.json> <out.json>
import { readFileSync, writeFileSync } from "node:fs";
import worker from "../src/index.js";

const [origin, questionsPath, outPath] = process.argv.slice(2);
const questions = JSON.parse(readFileSync(questionsPath, "utf8"));
let prompts = [];
const env = {
  ALLOWED_ORIGIN: "https://coszo.org",
  ATLAS_API_ORIGIN: origin,
  ATLAS_API_KEY: process.env.ATLAS_API_KEY,
  ATLAS_MAP_GATEWAY_ORIGIN: process.env.ATLAS_MAP_GATEWAY_ORIGIN || "http://127.0.0.1:8787",
  OOI_RELAY_TOKEN: "stub",
  OOI_RELAY: {
    fetch: async (_url, init) => {
      prompts.push(JSON.parse(init.body).messages.map((m) => m.content).join("\n"));
      return new Response(JSON.stringify({ choices: [{ message: { content: "stub answer [1]" } }] }), { headers: { "content-type": "application/json" } });
    },
  },
};
const out = [];
for (const { id, question } of questions) {
  prompts = [];
  const request = new Request("https://rca-atlas.local/v1/answer", {
    method: "POST", headers: { "content-type": "application/json", origin: "https://coszo.org" },
    body: JSON.stringify({ query: question, model: "ooi-gemma-4-26b" }),
  });
  let status, error;
  try {
    const res = await worker.fetch(request, env);
    status = res.status;
    if (!res.ok) error = (await res.json()).error;
  } catch (e) {
    error = String(e);
  }
  out.push({ id, question, status, error, prompt: prompts.join("\n\n") });
  process.stderr.write(`${id} ${status} ${prompts.join("").length} chars${error ? " " + error : ""}\n`);
}
writeFileSync(outPath, JSON.stringify(out));
