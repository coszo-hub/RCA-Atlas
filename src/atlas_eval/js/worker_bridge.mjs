// Runs the deployed Worker's own pure functions on eval inputs (JSON on stdin, JSON on stdout),
// so the baseline router and the JS hypo71 parser are scored exactly as they ship.
import { readFileSync } from "node:fs";
import { axialDayWindow, parseHypo71Events } from "../../atlas_worker/src/helpers.js";
import { answerMode, isDownloadQuestion, isInstrumentInventoryQuestion, namedDataProduct } from "../../atlas_worker/src/index.js";

const input = JSON.parse(readFileSync(0, "utf8"));

// The Worker's implicit task decision, in the order its fetch handler applies it.
function workerTask(question) {
  if (axialDayWindow(question, { now: new Date("2026-09-25T12:00:00Z") })) return "earthquake_count";
  if ((namedDataProduct(question) && isDownloadQuestion(question)) || answerMode(question) === "compact") return "data_download";
  if (isInstrumentInventoryQuestion(question)) return "instrument_inventory";
  return "general_research";
}

let output;
if (input.op === "route") output = input.questions.map(workerTask);
else if (input.op === "parse") output = input.files.map(([text, stamp]) => parseHypo71Events(text, stamp));
else if (input.op === "window") output = input.questions.map(([q, now, tz]) => {
  const w = axialDayWindow(q, { now: new Date(now), tz });
  return w && { day: w.day, start: w.start.toISOString(), end: w.end.toISOString() };
});
else throw new Error(`unknown op ${input.op}`);
process.stdout.write(JSON.stringify(output));
