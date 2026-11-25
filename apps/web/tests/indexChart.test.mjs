import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

const source = await readFile(new URL("../src/lib/indexChart.ts", import.meta.url), "utf8");
const compiled = ts.transpile(source, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 });
const { chartHistory, currentSignal, decisionChecks, epoch, formingBar, heikinAshiBar } = await import("data:text/javascript;base64," + Buffer.from(compiled).toString("base64"));

const raw = { timestamp: "2026-11-23T09:15:00+05:30", open: 100, high: 110, low: 90, close: 108 };
const next = { ...raw, timestamp: "2026-11-23T09:30:00+05:30", open: 111, high: 121, low: 110, close: 118 };
const forming = { ...next, timestamp: "2026-11-23T09:45:00+05:30", is_forming: true };
const series = { candles: [raw, next, forming], indicator_history: [
  { timestamp: raw.timestamp, decision: "SELL" }, { timestamp: next.timestamp, decision: "BUY" },
  { timestamp: next.timestamp, decision: "BUY" }, { timestamp: forming.timestamp, decision: "SELL" },
], feed_state: "live", is_stale: false, indicator_decision: { decision: "BUY", is_current_signal: true, candle_timestamp: next.timestamp } };
const tick = { available: true, feed_state: "live", is_stale: false, checked_at: "2026-11-23T09:47:00+05:30", quote: { ltp: 118 }, forming_candle: forming };

test("Heikin Ashi open, close and wick extremes use prior averaged prices; optional warm-up survives a window change", () => {
  const first = heikinAshiBar(raw);
  assert.deepEqual(first, { time: epoch(raw.timestamp), open: 104, close: 102, high: 110, low: 90 });
  assert.deepEqual(heikinAshiBar(next, first), { time: epoch(next.timestamp), open: 103, close: 115, high: 121, low: 103 });
  assert.deepEqual(chartHistory({ ...series, candles: [next], heikin_ashi_previous_open_close: [104,102] }).bars[0], heikinAshiBar(next, first));
});

test("only complete candles get markers, anchored on the correct displayed wick", () => {
  const { bars, marks } = chartHistory(series);
  assert.equal(bars.length, 2);
  assert.deepEqual(marks, [{ time: epoch(raw.timestamp), side: "SELL", price: 110 }, { time: epoch(next.timestamp), side: "BUY", price: 103 }]);
  const partial = chartHistory({ ...series, candles: [raw, { ...next, is_incomplete: true }] });
  assert.equal(partial.marks.length, 1);
});

test("the opening range and trend position are independent of a crossover or confirmed signal", () => {
  const decision = { decision: "WAIT", opening_range_state: "BELOW_LOW", ut_bot_position: -1,
    ut_bot_signal: null, ema_bullish: null, rsi_bullish: false, macd_bullish: true, supertrend_bullish: false };
  const readings = Object.fromEntries(decisionChecks(decision));
  assert.equal(readings["09:15 IST opening range"], "Close below low");
  assert.equal(readings["Trend position"], "Bearish");
  assert.equal(readings["Trend check A"], "Neutral");
  const warming = Object.fromEntries(decisionChecks({ ...decision, decision: "DATA_UNAVAILABLE", ut_bot_position: null }));
  assert.equal(warming["Trend check A"], "No reading");
  assert.equal(warming["Trend position"], "No reading");
  const legacy = Object.fromEntries(decisionChecks({ decision: "SELL", ut_bot_signal: "SELL" }));
  assert.equal(legacy["09:15 IST opening range"], "No reading");
  assert.equal(legacy["Trend position"], "No reading");
});

test("a stale, partial, older or rolled forming candle cannot supply a live signal", () => {
  const previous = chartHistory(series).bars.at(-1);
  assert.ok(currentSignal(series, tick) && formingBar(tick, previous));
  assert.equal(formingBar({ ...tick, forming_candle: { ...forming, is_incomplete: true } }, previous), null);
  for (const changed of [{ is_stale: true }, { feed_state: "closed" }, { available: false }, { checked_at: "2026-11-23T10:00:01+05:30" }]) {
    const quote = { ...tick, ...changed };
    assert.equal(currentSignal(series, quote), false);
    assert.equal(formingBar(quote, previous), null);
  }
  assert.equal(currentSignal({ ...series, is_stale: true }, tick), false);
  assert.equal(formingBar(tick, { ...previous, time: epoch(forming.timestamp) }), null);
});
