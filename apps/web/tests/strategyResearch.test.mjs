import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import * as jsxRuntime from "react/jsx-runtime";
import { renderToStaticMarkup } from "react-dom/server";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
function load(relative, imports = {}) {
  const filename = path.join(root, relative);
  const compiled = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    fileName: filename,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  });
  const moduleObj = { exports: {} };
  vm.runInNewContext(compiled.outputText, {
    module: moduleObj, exports: moduleObj.exports, Date, Number,
    require: (name) => {
      if (name === "react/jsx-runtime") return jsxRuntime;
      if (name in imports) return imports[name];
      throw new Error(`Unexpected import ${name}`);
    },
  });
  return moduleObj.exports;
}
const presentation = load("src/lib/strategyPresentation.ts");
const stamp = "2026-11-16T09:15:00+05:30";
const now = Date.parse("2026-11-16T09:21:00+05:30");
const decision = {
  decision: "BUY", is_current_signal: true, feed_state: "live", is_stale: false,
  candle_timestamp: stamp, evaluated_at: "2026-11-16T09:20:50+05:30", reason: "All checks agree.",
};

test("confirmed BUY needs a matching complete current candle and fresh evaluation", () => {
  const show = presentation.presentConfirmedDecision;
  assert.equal(show(decision, { timestamp: stamp }, true, now).signal, "BUY");
  for (const [changed, candle, current, time] of [
    [{ ...decision, is_current_signal: false }, { timestamp: stamp }, true, now],
    [{ ...decision, is_stale: true }, { timestamp: stamp }, true, now],
    [{ ...decision, feed_state: "closed" }, { timestamp: stamp }, true, now],
    [decision, { timestamp: stamp, is_incomplete: true }, true, now],
    [decision, { timestamp: "2026-11-16T09:10:00+05:30" }, true, now],
    [decision, { timestamp: stamp }, false, now],
    [decision, { timestamp: stamp }, true, now + 300_000],
    [{ ...decision, evaluated_at: "2026-11-16T09:19:00+05:30" }, { timestamp: stamp }, true, now],
    [{ ...decision, evaluated_at: "invalid" }, { timestamp: stamp }, true, now],
  ]) {
    assert.equal(show(changed, candle, current, time).signal, "WAIT");
    assert.equal(show(changed, candle, current, time).current, false);
  }
  assert.equal(show(null, undefined, false, now).signal, "DATA_UNAVAILABLE");
  const healthyWait = show({ ...decision, decision: "WAIT", is_current_signal: false, reason: "No unanimous confirmed signal." }, { timestamp: stamp }, true, now);
  assert.equal(healthyWait.signal, "WAIT");
  assert.equal(healthyWait.reason, "No unanimous confirmed signal.");
  assert.equal(healthyWait.current, true);
});

test("research directional observations never turn the displayed research decision into BUY", () => {
  const { default: Panel } = load("src/components/StrategyDecisionPanel.tsx", {
    "@/lib/strategyPresentation": presentation,
    "next/link": { default: ({ children, href, ...props }) => jsxRuntime.jsx("a", { ...props, href, children }) },
  });
  const html = renderToStaticMarkup(Panel({
    decision: null, latestConfirmed: undefined, feedCurrent: true, evaluatedNow: now,
    research: { version: "strategy-research-v1", status: "research_only", decision: "WAIT",
      candidate_decision: "BUY", candidate_is_current: true, is_current_signal: false,
      selected_strategy: "example", regime: "trending", adx: 25.1,
      reason: "Observed setup awaits verification.", evidence_status: "not_validated",
      candle_timestamp: stamp, evaluated_at: decision.evaluated_at,
      strategies: [{ id: "example", label: "Example rule", signal: "BUY" }],
    },
  }));
  assert.match(html, /Strategy research/);
  assert.match(html, />WAIT</);
  assert.match(html, /Research pending verification/);
  assert.match(html, /<details/);
  assert.match(html, /Upward setup observed/);
  assert.doesNotMatch(html, />BUY</);
});

test("zero-observation selection shows unavailable accuracy and source metrics stay explicit", () => {
  const { default: Report } = load("src/components/StrategyResearchReport.tsx");
  const html = renderToStaticMarkup(Report({ data: {
    version: "strategy-research-v1", audit_start: "2025-11-15", audit_end: "2026-11-14",
    horizon_minutes: 30, evidence_status: "exploratory_reused_data",
    walk_forward: { signals: 0, accuracy_pct: null, mean_gross_bps: null, mean_net_2bps: null, blocks: 10, wait_blocks: 10 },
    instruments: {},
  } }));
  assert.match(html, /N\/A/);
  assert.match(html, /10 \/ 10/);
  assert.match(html, /No qualifying test observations/);
  assert.match(html, /reuses the previously examined/);
  assert.doesNotMatch(html, /0\.00%/);
});
