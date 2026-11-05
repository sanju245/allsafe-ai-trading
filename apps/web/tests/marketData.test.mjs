import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { createRequire } from "node:module";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const webRoot = path.resolve(__dirname, "..");

const requireWithFallback = createRequire(
  fs.existsSync(path.join(webRoot, "node_modules", "@babel", "core"))
    ? path.join(webRoot, "node_modules", "index.js")
    : "/usr/share/nodejs/index.js",
);
const babel = requireWithFallback("@babel/core");

function loadTsModule(relPath) {
  const fullPath = path.join(webRoot, relPath);
  const code = fs.readFileSync(fullPath, "utf8");
  const transformed = babel.transformSync(code, {
    filename: fullPath,
    presets: [
      [
        requireWithFallback("@babel/preset-env"),
        { targets: { node: "current" }, modules: "commonjs" },
      ],
      requireWithFallback("@babel/preset-typescript"),
    ],
  });
  const exportsObj = {};
  const moduleObj = { exports: exportsObj };
  const sandbox = {
    exports: exportsObj,
    module: moduleObj,
    require: requireWithFallback,
    process,
    console,
    Intl,
    Date,
    Math,
    Number,
    Map,
    Set,
    Array,
    Object,
    String,
    Boolean,
    Error,
    Symbol,
    Promise,
    setTimeout,
    clearTimeout,
    AbortController,
  };
  vm.runInNewContext(transformed.code, sandbox, { filename: fullPath });
  return moduleObj.exports;
}

const marketData = loadTsModule("src/lib/marketData.ts");

test("formatPrice and formatInrCurrency format numbers in en-IN locale safely using singleton Intl formatters", () => {
  assert.equal(marketData.formatPrice(24350.5), "24,350.50");
  assert.equal(marketData.formatPrice(51234.126), "51,234.13");
  assert.equal(marketData.formatPrice(0), "0.00");
  assert.equal(marketData.formatPrice(null), "—");
  assert.equal(marketData.formatPrice(undefined), "—");
  assert.equal(marketData.formatPrice(Number.NaN), "—");
  assert.equal(marketData.formatPrice(Number.POSITIVE_INFINITY), "—");
  assert.ok(marketData.formatInrCurrency(200000).includes("2,00,000"));
  assert.ok(marketData.formatInrCurrency(1500000).includes("15,00,000"));
  assert.equal(marketData.formatInrCurrency(null), "—");
});

test("formatSignedDelta formats positive, negative, and flat index changes", () => {
  const up = marketData.formatSignedDelta(145.25, 0.6);
  assert.equal(up.direction, "up");
  assert.equal(up.pointsText, "+145.25");
  assert.equal(up.percentText, "+0.60%");
  assert.equal(up.text, "+145.25 (+0.60%)");

  const down = marketData.formatSignedDelta(-82.5, -0.34);
  assert.equal(down.direction, "down");
  assert.equal(down.pointsText, "−82.50");
  assert.equal(down.percentText, "−0.34%");
  assert.equal(down.text, "−82.50 (−0.34%)");

  const flat = marketData.formatSignedDelta(0, 0);
  assert.equal(flat.direction, "flat");
  assert.equal(flat.pointsText, "0.00");
});

test("formatIstTime formats UTC timestamps and Date objects into Asia/Kolkata IST 24-hour time", () => {
  assert.equal(
    marketData.formatIstTime("2026-10-30T04:00:00Z", { includeSeconds: false }),
    "09:30",
  );
  assert.equal(
    marketData.formatIstTime("2026-10-30T04:00:05Z", { includeSeconds: true }),
    "09:30:05",
  );
  assert.equal(
    marketData.formatIstTime(new Date("2026-10-30T09:45:30Z"), {
      includeSeconds: false,
    }),
    "15:15",
  );
  assert.equal(marketData.formatIstTime(null), "—");
  assert.equal(marketData.formatIstTime("invalid-date"), "—");
});

test("mergeAndSortCandles strictly separates confirmed candles from the forming candle", () => {
  const confirmed = [
    {
      timestamp: "2026-10-30T09:20:00+05:30",
      open: 24310,
      high: 24330,
      low: 24305,
      close: 24325,
      is_forming: false,
    },
    {
      timestamp: "2026-10-30T09:15:00+05:30",
      open: 24290,
      high: 24315,
      low: 24280,
      close: 24310,
      is_forming: false,
    },
    {
      timestamp: "2026-10-30T09:15:00+05:30",
      open: 24290,
      high: 24315,
      low: 24280,
      close: 24310,
      is_forming: false,
    },
  ];

  const forming = {
    timestamp: "2026-10-30T09:25:00+05:30",
    open: 24325,
    high: 24342,
    low: 24320,
    close: 24338,
    is_forming: true,
  };

  const result = marketData.mergeAndSortCandles(confirmed, forming);
  assert.equal(result.confirmedCandles.length, 2);
  assert.equal(
    result.confirmedCandles[0].timestamp,
    "2026-10-30T09:15:00+05:30",
  );
  assert.equal(
    result.confirmedCandles[1].timestamp,
    "2026-10-30T09:20:00+05:30",
  );
  assert.equal(
    result.confirmedCandles.every(
      (c) => c.is_confirmed === true && c.is_forming === false,
    ),
    true,
  );

  assert.ok(result.formingCandle);
  assert.equal(result.formingCandle.is_forming, true);
  assert.equal(result.formingCandle.is_confirmed, false);
  assert.equal(result.combinedCandles.length, 3);
  assert.equal(result.combinedCandles[2].is_forming, true);
});

test("mergeAndSortCandles drops forming candle if its slot is already confirmed", () => {
  const confirmed = [
    {
      timestamp: "2026-10-30T09:15:00+05:30",
      open: 24290,
      high: 24315,
      low: 24280,
      close: 24310,
      is_forming: false,
    },
  ];
  const staleForming = {
    timestamp: "2026-10-30T09:15:00+05:30",
    open: 24290,
    high: 24312,
    low: 24280,
    close: 24305,
    is_forming: true,
  };

  const result = marketData.mergeAndSortCandles(confirmed, staleForming);
  assert.equal(result.formingCandle, null);
  assert.equal(result.combinedCandles.length, 1);
  assert.equal(result.combinedCandles[0].close, 24310);
});

test("computeMarketStats computes accurate session OHLC, change, and range position", () => {
  const candles = [
    {
      timestamp: "2026-10-30T09:15:00+05:30",
      open: 24200,
      high: 24260,
      low: 24180,
      close: 24250,
      is_forming: false,
    },
    {
      timestamp: "2026-10-30T09:20:00+05:30",
      open: 24250,
      high: 24300,
      low: 24240,
      close: 24280,
      is_forming: false,
    },
    {
      timestamp: "2026-10-30T09:25:00+05:30",
      open: 24280,
      high: 24320,
      low: 24270,
      close: 24300,
      is_forming: true,
    },
  ];

  const stats = marketData.computeMarketStats(candles, {
    ltp: 24310,
    timestamp: "2026-10-30T09:26:10+05:30",
  });

  assert.equal(stats.latestPrice, 24310);
  assert.equal(stats.openPrice, 24200);
  assert.equal(stats.highPrice, 24320);
  assert.equal(stats.lowPrice, 24180);
  assert.equal(stats.changePoints, 110);
  assert.equal(stats.confirmedCount, 2);
  assert.ok(stats.formingCandle);
  assert.ok(stats.rangePositionPercent > 90 && stats.rangePositionPercent <= 100);
});

test("getFeedStateBadge maps backend feed states and staleness flags to semantic badges", () => {
  assert.equal(marketData.getFeedStateBadge("live", false).shortLabel, "LIVE");
  assert.equal(marketData.getFeedStateBadge("live", true).shortLabel, "STALE");
  assert.equal(
    marketData.getFeedStateBadge("closed", false).shortLabel,
    "CLOSED",
  );
  assert.equal(
    marketData.getFeedStateBadge("disconnected", false).shortLabel,
    "OFFLINE",
  );
  assert.equal(
    marketData.getFeedStateBadge("failed", false).shortLabel,
    "ERROR",
  );
});

test("getDecisionBadge and getAIRecommendationBadge lock signals when feed is non-live or stale", () => {
  const activeBuy = marketData.getDecisionBadge({
    decision: "BUY",
    is_current_signal: true,
    feed_state: "live",
    is_stale: false,
    reason: "All 5 indicators aligned bullish.",
    confirmed_candle_count: 45,
  });
  assert.equal(activeBuy.label, "BUY SIGNAL");
  assert.equal(activeBuy.isActionable, true);
  assert.equal(activeBuy.tone, "emerald");

  const staleBuy = marketData.getDecisionBadge({
    decision: "BUY",
    is_current_signal: false,
    feed_state: "stale",
    is_stale: true,
    reason: "Stale feed.",
    confirmed_candle_count: 45,
  });
  assert.equal(staleBuy.label, "BUY (HISTORICAL)");
  assert.equal(staleBuy.isActionable, false);
  assert.equal(staleBuy.tone, "amber");

  const aiLongLive = marketData.getAIRecommendationBadge({
    recommendation: "LONG_SETUP",
    is_live_actionable: true,
    is_stale: false,
  });
  assert.equal(aiLongLive.label, "LONG SETUP");
  assert.equal(aiLongLive.isActionable, true);

  const aiLongStale = marketData.getAIRecommendationBadge({
    recommendation: "LONG_SETUP",
    is_live_actionable: false,
    is_stale: true,
  });
  assert.equal(aiLongStale.label, "LONG SETUP (HISTORICAL)");
  assert.equal(aiLongStale.isActionable, false);

  const aiNoTrade = marketData.getAIRecommendationBadge({
    recommendation: "NO_TRADE",
    is_live_actionable: false,
    is_stale: false,
  });
  assert.equal(aiNoTrade.label, "NO TRADE");
  assert.equal(aiNoTrade.isActionable, false);
});

test("computeClientPositionSizing enforces max risk cap and lot size multiples", () => {
  const sizing = marketData.computeClientPositionSizing(
    300000,
    4.0, // exceeds 2.0% cap
    24500,
    24460, // 40 pts risk
    75, // NIFTY lot size
    2.0,
  );
  assert.equal(sizing.exceeded_max_risk_cap, true);
  assert.equal(sizing.effective_risk_pct, 2.0);
  assert.equal(sizing.max_risk_amount_inr, 6000);
  assert.equal(sizing.recommended_lots, 2); // 150 units * 40 = 6000
  assert.equal(sizing.recommended_quantity, 150);
  assert.equal(sizing.actual_risk_amount_inr, 6000);
});

test("classifyFetchError categorizes auth (401/403), gateway (502/503), and rate-limit (429) errors", () => {
  const authErr = marketData.classifyFetchError(
    new Error("Market data request failed (HTTP 403)."),
  );
  assert.equal(authErr.statusCode, 403);
  assert.equal(authErr.isAuthError, true);

  const gatewayErr = marketData.classifyFetchError(
    new Error("Market data request failed (HTTP 502)."),
  );
  assert.equal(gatewayErr.statusCode, 502);
  assert.equal(gatewayErr.isAuthError, false);
});

test("Phase 3 P2-A4: Capital input debouncing, empty/invalid/partial draft preservation, blur fallback, and unmount cleanup", async () => {
  assert.equal(marketData.CAPITAL_DEBOUNCE_MS, 250);
  assert.equal(marketData.MIN_ACCOUNT_CAPITAL, 25000);
  assert.equal(marketData.MAX_ACCOUNT_CAPITAL, 50000000);
  assert.equal(marketData.DEFAULT_ACCOUNT_CAPITAL, 200000);

  // Full edge-case matrix for sanitizeAccountCapital (used on blur / final commit)
  assert.equal(marketData.sanitizeAccountCapital(25000), 25000);
  assert.equal(marketData.sanitizeAccountCapital(50000000), 50000000);
  assert.equal(marketData.sanitizeAccountCapital("500000"), 500000);
  assert.equal(marketData.sanitizeAccountCapital(10000), 25000); // clamped to min 25,000 on blur
  assert.equal(marketData.sanitizeAccountCapital("15000"), 25000); // clamped to min 25,000 on blur
  assert.equal(marketData.sanitizeAccountCapital(99999999), 50000000); // clamped to max 50,000,000 on blur
  assert.equal(marketData.sanitizeAccountCapital(0), 200000);
  assert.equal(marketData.sanitizeAccountCapital(-50000), 200000);
  assert.equal(marketData.sanitizeAccountCapital(""), 200000);
  assert.equal(marketData.sanitizeAccountCapital("   "), 200000);
  assert.equal(marketData.sanitizeAccountCapital("abc"), 200000);
  assert.equal(marketData.sanitizeAccountCapital(null), 200000);
  assert.equal(marketData.sanitizeAccountCapital(undefined), 200000);
  assert.equal(marketData.sanitizeAccountCapital(Number.NaN), 200000);
  assert.equal(marketData.sanitizeAccountCapital(Number.POSITIVE_INFINITY), 200000);
  assert.equal(marketData.sanitizeAccountCapital(Number.NEGATIVE_INFINITY), 200000);

  // Blurring an empty or invalid input preserves the user's current committed capital (e.g. 500,000) instead of resetting to 200,000
  assert.equal(marketData.sanitizeAccountCapital("", 500000), 500000);
  assert.equal(marketData.sanitizeAccountCapital("   ", 500000), 500000);
  assert.equal(marketData.sanitizeAccountCapital("abc", 500000), 500000);
  assert.equal(marketData.sanitizeAccountCapital(0, 500000), 500000);

  // Mid-typing draft parser (parseDraftAccountCapital) returns null on empty, invalid, AND partially typed values (< 25,000)
  // so typing "5", "50", "500", "5000" on the way to "500000" never resets accountCapital to 25,000 or 200,000
  assert.equal(marketData.parseDraftAccountCapital(""), null);
  assert.equal(marketData.parseDraftAccountCapital("   "), null);
  assert.equal(marketData.parseDraftAccountCapital("-"), null);
  assert.equal(marketData.parseDraftAccountCapital("0"), null);
  assert.equal(marketData.parseDraftAccountCapital("5"), null);
  assert.equal(marketData.parseDraftAccountCapital("50"), null);
  assert.equal(marketData.parseDraftAccountCapital("500"), null);
  assert.equal(marketData.parseDraftAccountCapital("5000"), null);
  assert.equal(marketData.parseDraftAccountCapital("15000"), null);
  assert.equal(marketData.parseDraftAccountCapital("25000."), null);
  assert.equal(marketData.parseDraftAccountCapital("25000"), 25000);
  assert.equal(marketData.parseDraftAccountCapital("350000"), 350000);
  assert.equal(marketData.parseDraftAccountCapital("99999999"), 50000000);

  const committedValues = [];
  const debounced = marketData.createDebouncedCallback((val) => {
    committedValues.push(val);
  }, 40);

  // Simulate typing 5, 50, 500, 5000, 50000, 500000 rapidly
  for (const raw of ["5", "50", "500", "5000", "50000", "500000"]) {
    const parsed = marketData.parseDraftAccountCapital(raw);
    if (parsed === null) {
      debounced.cancel();
    } else {
      debounced.trigger(parsed);
    }
  }

  assert.equal(debounced.isPending(), true);
  assert.equal(committedValues.length, 0);

  await new Promise((r) => setTimeout(r, 65));
  assert.equal(debounced.isPending(), false);
  assert.deepEqual(committedValues, [500000]);

  // Simulate user clearing input ("") or typing partial ("3", "300") during editing: does not reset committed 500,000
  for (const draft of ["", "3", "30", "300", "3000"]) {
    const parsed = marketData.parseDraftAccountCapital(draft);
    assert.equal(parsed, null);
    debounced.cancel();
  }
  await new Promise((r) => setTimeout(r, 60));
  assert.deepEqual(committedValues, [500000]);

  // Simulate unmount / blur cancellation while a debounce timer is pending
  debounced.trigger(750000);
  assert.equal(debounced.isPending(), true);
  debounced.cancel();
  assert.equal(debounced.isPending(), false);
  await new Promise((r) => setTimeout(r, 60));
  assert.deepEqual(committedValues, [500000]);
});

test("Phase 3 P2-A1: Request deduplication, subscriber cancellation isolation, full-abort cleanup, and zero memory leaks", async () => {
  const dedup = marketData.createInFlightGetDeduplicator();
  let networkCalls = 0;

  const fetchCandles = (capital, riskPct, signal) => {
    const key = `tok::/api/v1/live/candles?symbol=NIFTY50&capital=${capital}&risk_pct=${riskPct}`;
    return dedup.request(
      key,
      async (sharedSignal) => {
        networkCalls += 1;
        const callNumber = networkCalls;
        return new Promise((resolve, reject) => {
          const timer = setTimeout(() => {
            resolve({ capital, riskPct, callNumber });
          }, 40);
          sharedSignal.addEventListener(
            "abort",
            () => {
              clearTimeout(timer);
              reject(new Error("Underlying fetch aborted."));
            },
            { once: true },
          );
        });
      },
      signal,
    );
  };

  // 1. Two concurrent identical requests where Caller A aborts and Caller B stays active:
  // Caller A rejects immediately with AbortError, while the shared underlying fetch is NOT cancelled and resolves for Caller B!
  const ctrlA = new AbortController();
  const ctrlB = new AbortController();

  const promiseA = fetchCandles(200000, 1.0, ctrlA.signal);
  const promiseB = fetchCandles(200000, 1.0, ctrlB.signal);
  assert.equal(dedup.getInFlightCount(), 1);
  assert.equal(dedup.getSubscriberCount(), 2);

  setTimeout(() => ctrlA.abort(), 10);

  await assert.rejects(promiseA, (err) => {
    assert.equal(err.name, "AbortError");
    assert.match(err.message, /Request aborted/);
    return true;
  });
  const resultB = await promiseB;
  assert.equal(networkCalls, 1);
  assert.deepEqual(resultB, { capital: 200000, riskPct: 1.0, callNumber: 1 });
  assert.equal(dedup.getInFlightCount(), 0);
  assert.equal(dedup.getSubscriberCount(), 0);

  // 2. When ALL subscribers sharing a request abort, the underlying sharedSignal aborts and cleans up immediately
  let sharedSignalAborted = false;
  const ctrlC = new AbortController();
  const ctrlD = new AbortController();
  const keyAllAbort = "tok::/api/v1/live/status";
  const pC = dedup.request(
    keyAllAbort,
    (sharedSignal) =>
      new Promise((resolve, reject) => {
        sharedSignal.addEventListener(
          "abort",
          () => {
            sharedSignalAborted = true;
            reject(new Error("Underlying shared fetch aborted."));
          },
          { once: true },
        );
      }),
    ctrlC.signal,
  );
  const pD = dedup.request(
    keyAllAbort,
    () => Promise.resolve({ ok: true }),
    ctrlD.signal,
  );

  assert.equal(dedup.getSubscriberCount(keyAllAbort), 2);
  ctrlC.abort();
  assert.equal(sharedSignalAborted, false); // D is still subscribed!
  assert.equal(dedup.getInFlightCount(), 1);
  assert.equal(dedup.getSubscriberCount(keyAllAbort), 1);

  ctrlD.abort();
  assert.equal(sharedSignalAborted, true); // Last subscriber aborted -> sharedSignal aborted!
  assert.equal(dedup.getInFlightCount(), 0);
  assert.equal(dedup.getSubscriberCount(keyAllAbort), 0);
  await assert.rejects(pC, /Request aborted/);
  await assert.rejects(pD, /Request aborted/);

  // 3. Pre-aborted signal rejects immediately without calling fetcher
  const preAborted = new AbortController();
  preAborted.abort();
  let calledOnPreAborted = false;
  await assert.rejects(
    dedup.request(
      "tok::/api/v1/live/pre-aborted",
      async () => {
        calledOnPreAborted = true;
        return { ok: true };
      },
      preAborted.signal,
    ),
    /Request aborted/,
  );
  assert.equal(calledOnPreAborted, false);
  assert.equal(dedup.getInFlightCount(), 0);

  // 4. Underlying fetch error rejects all subscribers and cleans up in-flight map & subscriber references
  const errKey = "tok::/api/v1/live/error-case";
  const errP1 = dedup.request(errKey, async () => {
    await new Promise((r) => setTimeout(r, 15));
    throw new Error("Simulated HTTP 503 failure");
  });
  const errP2 = dedup.request(errKey, async () => ({ ok: true }));
  assert.equal(dedup.getInFlightCount(), 1);
  assert.equal(dedup.getSubscriberCount(errKey), 2);
  await assert.rejects(errP1, /Simulated HTTP 503 failure/);
  await assert.rejects(errP2, /Simulated HTTP 503 failure/);
  assert.equal(dedup.getInFlightCount(), 0);
  assert.equal(dedup.getSubscriberCount(errKey), 0);

  // 5. Concurrent requests with different capital/riskPct NEVER collide or return stale parameters
  const [resCap200k, resCap500k, resRisk2Pct] = await Promise.all([
    fetchCandles(200000, 1.0),
    fetchCandles(500000, 1.0),
    fetchCandles(500000, 2.0),
  ]);
  assert.equal(resCap200k.capital, 200000);
  assert.equal(resCap500k.capital, 500000);
  assert.equal(resCap500k.riskPct, 1.0);
  assert.equal(resRisk2Pct.capital, 500000);
  assert.equal(resRisk2Pct.riskPct, 2.0);
  assert.equal(dedup.getInFlightCount(), 0);
  assert.equal(dedup.getSubscriberCount(), 0);
});

test("Phase 3 P2-A2: Adaptive polling transitions and Closed -> Open forming-candle recovery fetch", () => {
  assert.equal(marketData.LIVE_POLL_INTERVAL_MS, 15000);
  assert.equal(marketData.OFF_HOURS_POLL_INTERVAL_MS, 60000);

  // Initial state (status === null): 15s polling and fetch forming candle
  assert.equal(marketData.getAdaptivePollIntervalMs(null), 15000);
  assert.equal(marketData.shouldFetchFormingCandle(null, "NIFTY50"), true);

  // Market Open + Live stream: 15s polling and fetch forming candle
  const liveStatus = {
    feed_state: "live",
    streaming_enabled: true,
    connected: true,
    session_open: true,
    last_error: null,
    instruments: {
      NIFTY50: { feed_state: "live", has_forming_candle: true },
      BANKNIFTY: { feed_state: "live", has_forming_candle: false },
    },
  };
  assert.equal(marketData.getAdaptivePollIntervalMs(liveStatus), 15000);
  assert.equal(
    marketData.shouldFetchFormingCandle(liveStatus, "NIFTY50"),
    true,
  );
  assert.equal(
    marketData.shouldFetchFormingCandle(liveStatus, "BANKNIFTY"),
    true,
  );

  // Market Closed + no forming candle: steps down to 60s and skips forming-candle fetch
  const closedStatus = {
    feed_state: "closed",
    streaming_enabled: true,
    connected: false,
    session_open: false,
    last_error: null,
    instruments: {
      NIFTY50: { feed_state: "closed", has_forming_candle: false },
      BANKNIFTY: { feed_state: "closed", has_forming_candle: false },
    },
  };
  assert.equal(marketData.getAdaptivePollIntervalMs(closedStatus), 60000);
  const initialFetchWhenClosed = marketData.shouldFetchFormingCandle(
    closedStatus,
    "NIFTY50",
  );
  assert.equal(initialFetchWhenClosed, false);

  // While still closed on the current poll: recovery fetch is NOT triggered
  assert.equal(
    marketData.needsFormingCandleRecoveryFetch(
      initialFetchWhenClosed,
      { has_forming_candle: false, feed_state: "closed" },
      closedStatus,
      "NIFTY50",
      { feed_state: "closed" },
    ),
    false,
  );

  // Closed -> Open transition (P2-A2): priorStatus was closed, but current poll returns
  // candleResponse.has_forming_candle === true OR latestStatus.session_open === true OR quoteResponse.feed_state === "live":
  // recovery fetch triggers immediately on the transition poll cycle!
  assert.equal(
    marketData.needsFormingCandleRecoveryFetch(
      initialFetchWhenClosed,
      { has_forming_candle: true, feed_state: "live" },
      closedStatus,
      "NIFTY50",
    ),
    true,
  );
  assert.equal(
    marketData.needsFormingCandleRecoveryFetch(
      initialFetchWhenClosed,
      { has_forming_candle: false, feed_state: "checking" },
      liveStatus,
      "NIFTY50",
    ),
    true,
  );
  assert.equal(
    marketData.needsFormingCandleRecoveryFetch(
      initialFetchWhenClosed,
      { has_forming_candle: false, feed_state: "closed" },
      closedStatus,
      "NIFTY50",
      { feed_state: "live" },
    ),
    true,
  );
});

test("Phase 3 P2-A5: Refresh lifecycle — manual refresh queuing, cancellation safety, token switching, auto-refresh toggles, and unmount cleanup", async () => {
  let latestParams = { accountCapital: 200000, riskPct: 1.0 };
  let currentToken = "token-A";
  const executedCycles = [];
  const refreshingStates = [];
  const autoRefreshStates = [];

  const coordinator = marketData.createRefreshCoordinator(
    async (requestParams, ctx) => {
      executedCycles.push({
        ...requestParams,
        accessToken: ctx.accessToken,
      });
      await new Promise((resolve) => {
        const timer = setTimeout(resolve, 35);
        ctx.signal.addEventListener(
          "abort",
          () => {
            clearTimeout(timer);
            resolve();
          },
          { once: true },
        );
      });
    },
    () => latestParams,
    {
      getAccessToken: () => currentToken,
      initialAutoRefresh: true,
      onRefreshingChange: (val) => refreshingStates.push(val),
      onAutoRefreshChange: (val) => autoRefreshStates.push(val),
    },
  );

  // 1. In-flight capital/risk parameter update & manual refresh queuing (no overlapping cycles, no lost request)
  const cycle1Promise = coordinator.trigger();
  assert.equal(coordinator.isFetching(), true);
  assert.equal(coordinator.isRefreshing(), true);

  await new Promise((r) => setTimeout(r, 10));
  latestParams = { accountCapital: 500000, riskPct: 1.5 };
  // Manual refresh during active request queues pendingRefresh without overlapping
  void coordinator.trigger();
  assert.equal(coordinator.hasPendingRefresh(), true);
  assert.equal(executedCycles.length, 1);

  await cycle1Promise;
  assert.equal(coordinator.isFetching(), false);
  assert.equal(coordinator.isRefreshing(), false);
  assert.equal(coordinator.hasPendingRefresh(), false);
  assert.deepEqual(executedCycles, [
    { accountCapital: 200000, riskPct: 1.0, accessToken: "token-A" },
    { accountCapital: 500000, riskPct: 1.5, accessToken: "token-A" },
  ]);

  // 2. Cancelled request must NEVER leave isRefreshing permanently true
  const cancelledCycle = coordinator.trigger();
  assert.equal(coordinator.isRefreshing(), true);
  assert.equal(coordinator.isFetching(), true);
  coordinator.cancel({ clearPending: true });
  assert.equal(coordinator.isRefreshing(), false);
  assert.equal(coordinator.isFetching(), false);
  assert.equal(coordinator.hasPendingRefresh(), false);
  await cancelledCycle;
  assert.equal(coordinator.isRefreshing(), false);
  assert.equal(coordinator.isFetching(), false);

  // 3. Switching access tokens during an active refresh aborts token-A and immediately allows token-B to run
  const tokenACycle = coordinator.trigger();
  assert.equal(coordinator.getActiveToken(), "token-A");
  assert.equal(coordinator.isFetching(), true);

  // Switch token while token-A is still in flight
  currentToken = "token-B";
  coordinator.setAccessToken("token-B");
  const tokenBCycle = coordinator.trigger();
  assert.equal(coordinator.getActiveToken(), "token-B");
  assert.equal(coordinator.isFetching(), true);
  assert.equal(coordinator.isRefreshing(), true);

  await Promise.all([tokenACycle, tokenBCycle]);
  assert.equal(coordinator.isFetching(), false);
  assert.equal(coordinator.isRefreshing(), false);
  assert.equal(executedCycles[executedCycles.length - 1].accessToken, "token-B");

  // 4. Auto-refresh toggle transitions (true -> false pauses without refresh; false -> true enables and triggers refresh)
  const countBeforePause = executedCycles.length;
  const pausedState = coordinator.toggleAutoRefresh();
  assert.equal(pausedState, false);
  assert.equal(coordinator.isAutoRefreshEnabled(), false);
  assert.equal(executedCycles.length, countBeforePause); // Pausing does not trigger a fetch

  const resumedState = coordinator.toggleAutoRefresh();
  assert.equal(resumedState, true);
  assert.equal(coordinator.isAutoRefreshEnabled(), true);
  await new Promise((r) => setTimeout(r, 50));
  assert.equal(executedCycles.length, countBeforePause + 1); // Resuming triggers an immediate refresh
  assert.deepEqual(autoRefreshStates, [false, true]);

  // 5. Component unmount aborts active refresh, clears pending refresh, and prevents post-unmount runs
  const unmountCycle = coordinator.trigger();
  void coordinator.trigger(); // queue pending refresh
  assert.equal(coordinator.hasPendingRefresh(), true);
  const countAtUnmount = executedCycles.length;
  coordinator.unmount();
  assert.equal(coordinator.isFetching(), false);
  assert.equal(coordinator.isRefreshing(), false);
  assert.equal(coordinator.hasPendingRefresh(), false);
  await unmountCycle;
  await new Promise((r) => setTimeout(r, 50));
  assert.equal(executedCycles.length, countAtUnmount);
});

test("Phase 3 P2-A3 & P2-A5: LiveMarketDashboard and all dashboard components enforce pure state updaters, React.memo, and stale-on-error safety", () => {
  const filesToVerify = [
    "src/lib/api.ts",
    "src/lib/marketData.ts",
    "src/components/ApiStatus.tsx",
    "src/components/LiveMarketDashboard.tsx",
    "src/components/dashboard/ConnectionStatusBanner.tsx",
    "src/components/dashboard/MarketWatchlist.tsx",
    "src/components/dashboard/CandlestickChart.tsx",
    "src/components/dashboard/IndicatorDecisionPanel.tsx",
    "src/components/dashboard/MarketIntelligencePanel.tsx",
    "src/components/dashboard/MarketSkeleton.tsx",
    "src/app/layout.tsx",
    "src/app/page.tsx",
  ];

  for (const rel of filesToVerify) {
    const fullPath = path.join(webRoot, rel);
    assert.equal(fs.existsSync(fullPath), true, `Expected ${rel} to exist`);
    const source = fs.readFileSync(fullPath, "utf8");
    const result = babel.transformSync(source, {
      filename: fullPath,
      presets: [
        requireWithFallback("@babel/preset-typescript"),
        [requireWithFallback("@babel/preset-react"), { runtime: "automatic" }],
      ],
    });
    assert.ok(
      result && result.code && result.code.length > 0,
      `Failed to compile ${rel}`,
    );
  }

  // Verify React.memo wrapping on the dashboard components
  const memoizedComponents = [
    ["src/components/LiveMarketDashboard.tsx", /const\s+MarketCard\s*=\s*memo\(/],
    [
      "src/components/dashboard/ConnectionStatusBanner.tsx",
      /export\s+default\s+memo\(\s*ConnectionStatusBanner\s*\)/,
    ],
    [
      "src/components/dashboard/CandlestickChart.tsx",
      /export\s+default\s+memo\(\s*CandlestickChart\s*\)/,
    ],
    [
      "src/components/dashboard/IndicatorDecisionPanel.tsx",
      /export\s+default\s+memo\(\s*IndicatorDecisionPanel\s*\)/,
    ],
    [
      "src/components/dashboard/MarketIntelligencePanel.tsx",
      /export\s+default\s+memo\(\s*MarketIntelligencePanel\s*\)/,
    ],
    [
      "src/components/dashboard/MarketWatchlist.tsx",
      /export\s+default\s+memo\(\s*MarketWatchlist\s*\)/,
    ],
  ];

  for (const [rel, pattern] of memoizedComponents) {
    const content = fs.readFileSync(path.join(webRoot, rel), "utf8");
    assert.match(
      content,
      pattern,
      `Expected ${rel} to wrap component in React.memo`,
    );
  }

  // P2-A3 & P2-A5 static AST/source verification on LiveMarketDashboard.tsx:
  // 1. setAutoRefresh must NEVER contain void refresh() or any side-effecting function call
  const dashboardSrc = fs.readFileSync(
    path.join(webRoot, "src/components/LiveMarketDashboard.tsx"),
    "utf8",
  );
  assert.doesNotMatch(
    dashboardSrc,
    /setAutoRefresh\s*\(\s*\([^)]*\)\s*=>\s*\{[\s\S]*?refresh\s*\(/,
    "setAutoRefresh updater callback must never call refresh()",
  );
  assert.match(
    dashboardSrc,
    /const\s+handleToggleAutoRefresh\s*=\s*useCallback\(\(\)\s*=>\s*\{\s*const\s+next\s*=\s*!autoRefreshRef\.current;\s*autoRefreshRef\.current\s*=\s*next;\s*setAutoRefresh\(next\);\s*if\s*\(next\)\s*\{\s*void\s+refresh\(\);\s*\}\s*\}/,
    "handleToggleAutoRefresh must update autoRefresh purely and call refresh() outside setAutoRefresh",
  );

  // 2. Verify cancelActiveRefresh and finally block always reset isRefreshing(false) and isFetchingRef.current = false
  assert.match(dashboardSrc, /const\s+cancelActiveRefresh\s*=\s*useCallback/);
  assert.match(
    dashboardSrc,
    /if\s*\(abortControllerRef\.current\s*===\s*controller\)\s*\{\s*abortControllerRef\.current\s*=\s*null;\s*activeTokenRef\.current\s*=\s*null;\s*isFetchingRef\.current\s*=\s*false;\s*if\s*\(isMountedRef\.current\)\s*\{\s*setIsRefreshing\(false\);\s*\}/,
    "finally block must always reset isFetchingRef.current and setIsRefreshing(false) even when aborted",
  );

  // 3. Verify failed market poll marks cached data as stale and locks signals (is_current_signal: false, is_live_actionable: false)
  assert.match(dashboardSrc, /is_current_signal:\s*false/);
  assert.match(dashboardSrc, /is_live_actionable:\s*false/);
});

test("Phase 3 P2-A3 & P2-A5 Runtime Component Test: LiveMarketDashboard executes refresh, handleToggleAutoRefresh, manual refresh queuing, accessToken switching, cancellation, stale-on-error, and unmount under Strict Mode", async () => {
  const states = [];
  const refs = [];
  const effects = [];
  const cleanups = [];
  let hookCursor = 0;
  let inStateUpdater = false;
  let currentAuth = { token: "token-1", session: { access_token: "token-1" } };
  const fetchLog = [];
  let activeFetchResolvers = [];

  const mockReact = {
    memo: (fn) => fn,
    useState: (init) => {
      const idx = hookCursor++;
      if (!(idx in states)) {
        states[idx] = typeof init === "function" ? init() : init;
      }
      const setter = (valOrUpdater) => {
        if (typeof valOrUpdater === "function") {
          const prev = states[idx];
          inStateUpdater = true;
          try {
            // React Strict Mode double-invocation of functional state updaters
            const first = valOrUpdater(prev);
            const second = valOrUpdater(prev);
            assert.deepEqual(
              first,
              second,
              "State updater must be pure and idempotent under Strict Mode",
            );
            states[idx] = first;
          } finally {
            inStateUpdater = false;
          }
        } else {
          states[idx] = valOrUpdater;
        }
      };
      return [states[idx], setter];
    },
    useRef: (init) => {
      const idx = hookCursor++;
      if (!(idx in refs)) {
        refs[idx] = { current: init };
      }
      return refs[idx];
    },
    useCallback: (fn, deps) => {
      const idx = hookCursor++;
      if (!(idx in refs)) {
        refs[idx] = { value: fn, deps };
      } else {
        const prevDeps = refs[idx].deps;
        const changed =
          !prevDeps ||
          !deps ||
          deps.length !== prevDeps.length ||
          deps.some((d, i) => !Object.is(d, prevDeps[i]));
        if (changed) {
          refs[idx] = { value: fn, deps };
        }
      }
      return refs[idx].value;
    },
    useMemo: (fn, deps) => {
      const idx = hookCursor++;
      if (!(idx in refs)) {
        refs[idx] = { value: fn(), deps };
      } else {
        const prevDeps = refs[idx].deps;
        const changed =
          !prevDeps ||
          !deps ||
          deps.length !== prevDeps.length ||
          deps.some((d, i) => !Object.is(d, prevDeps[i]));
        if (changed) {
          refs[idx] = { value: fn(), deps };
        }
      }
      return refs[idx].value;
    },
    useEffect: (fn, deps) => {
      const idx = hookCursor++;
      const prev = effects[idx];
      const changed =
        !prev ||
        !deps ||
        deps.length !== prev.deps.length ||
        deps.some((d, i) => !Object.is(d, prev.deps[i]));
      effects[idx] = { fn, deps, changed };
    },
    jsx: (type, props, key) => ({ type, props, key }),
    jsxs: (type, props, key) => ({ type, props, key }),
    Fragment: "Fragment",
  };

  let shouldFailCandles = false;

  const mockFetch = (url, opts = {}) => {
    assert.equal(
      inStateUpdater,
      false,
      `fetch(${url}) must NEVER be triggered inside a React state updater!`,
    );
    const authHeader = opts.headers?.Authorization ?? "";
    const signal = opts.signal;
    const record = { url, authHeader, aborted: false };
    fetchLog.push(record);

    return new Promise((resolve, reject) => {
      const entry = {
        url,
        authHeader,
        signal,
        proceed: () => {
          if (signal?.aborted) {
            record.aborted = true;
            const err = new Error("Aborted");
            err.name = "AbortError";
            reject(err);
            return;
          }
          if (url.includes("/api/v1/live/status")) {
            resolve({
              ok: true,
              status: 200,
              json: async () => ({
                feed_state: "live",
                streaming_enabled: true,
                connected: true,
                session_open: true,
                last_error: null,
                instruments: {
                  NIFTY50: { feed_state: "live", has_forming_candle: true },
                  BANKNIFTY: { feed_state: "live", has_forming_candle: true },
                },
              }),
            });
          } else if (url.includes("/api/v1/live/candles")) {
            if (shouldFailCandles) {
              resolve({ ok: false, status: 503, json: async () => ({}) });
              return;
            }
            resolve({
              ok: true,
              status: 200,
              json: async () => ({
                candles: [
                  {
                    timestamp: "2026-10-30T09:15:00+05:30",
                    open: 24200,
                    high: 24250,
                    low: 24190,
                    close: 24240,
                    is_forming: false,
                  },
                ],
                feed_state: "live",
                is_stale: false,
                has_forming_candle: true,
                indicator_decision: {
                  decision: "BUY",
                  is_current_signal: true,
                  feed_state: "live",
                  is_stale: false,
                  reason: "All 5 indicators bullish.",
                  confirmed_candle_count: 1,
                },
                market_intelligence: {
                  recommendation: "LONG_SETUP",
                  is_live_actionable: true,
                  is_stale: false,
                  market_regime: "BULLISH",
                  trend_direction: "UPTREND",
                  headline_summary: "Bullish alignment",
                },
                message: "Live market-data feed is active.",
              }),
            });
          } else if (url.includes("/api/v1/live/quote")) {
            resolve({
              ok: true,
              status: 200,
              json: async () => ({
                available: true,
                feed_state: "live",
                is_stale: false,
                age_seconds: 2,
                quote: {
                  ltp: 24245,
                  timestamp: "2026-10-30T09:21:00+05:30",
                },
              }),
            });
          } else if (url.includes("/api/v1/live/forming-candle")) {
            resolve({
              ok: true,
              status: 200,
              json: async () => ({
                available: true,
                forming_candle: {
                  timestamp: "2026-10-30T09:20:00+05:30",
                  open: 24240,
                  high: 24255,
                  low: 24235,
                  close: 24245,
                  is_forming: true,
                },
              }),
            });
          }
        },
      };
      if (signal) {
        signal.addEventListener(
          "abort",
          () => {
            record.aborted = true;
            const err = new Error("Aborted");
            err.name = "AbortError";
            reject(err);
          },
          { once: true },
        );
      }
      activeFetchResolvers.push(entry);
    });
  };

  const flushActiveFetches = async () => {
    // Flush in waves because forming-candle recovery or parallel promises may chain
    for (let wave = 0; wave < 4; wave++) {
      const batch = activeFetchResolvers.splice(0, activeFetchResolvers.length);
      for (const item of batch) {
        item.proceed();
      }
      await new Promise((r) => setTimeout(r, 10));
    }
  };

  const fullPath = path.join(webRoot, "src/components/LiveMarketDashboard.tsx");
  const code = fs.readFileSync(fullPath, "utf8");
  const transformed = babel.transformSync(code, {
    filename: fullPath,
    presets: [
      [
        requireWithFallback("@babel/preset-env"),
        { targets: { node: "current" }, modules: "commonjs" },
      ],
      requireWithFallback("@babel/preset-typescript"),
      [requireWithFallback("@babel/preset-react"), { runtime: "automatic" }],
    ],
  });

  const customRequire = (id) => {
    if (id === "react" || id === "react/jsx-runtime") return mockReact;
    if (id === "@/components/auth/AuthProvider") {
      return { useAuth: () => currentAuth };
    }
    if (id === "@/lib/marketData") return marketData;
    if (id === "@/components/dashboard/ConnectionStatusBanner") {
      return { __esModule: true, default: "ConnectionStatusBanner" };
    }
    if (id === "@/components/dashboard/CandlestickChart") {
      return { __esModule: true, default: "CandlestickChart" };
    }
    if (id === "@/components/dashboard/IndicatorDecisionPanel") {
      return { __esModule: true, default: "IndicatorDecisionPanel" };
    }
    if (id === "@/components/dashboard/MarketIntelligencePanel") {
      return { __esModule: true, default: "MarketIntelligencePanel" };
    }
    if (id === "@/components/dashboard/MarketWatchlist") {
      return { __esModule: true, default: "MarketWatchlist" };
    }
    if (id === "@/components/dashboard/MarketSkeleton") {
      return {
        MarketCardSkeleton: "MarketCardSkeleton",
        MarketEmptyState: "MarketEmptyState",
        MarketErrorBanner: "MarketErrorBanner",
      };
    }
    return requireWithFallback(id);
  };

  const exportsObj = {};
  const moduleObj = { exports: exportsObj };
  const windowStub = {
    setInterval: () => 101,
    clearInterval: () => {},
  };
  const documentStub = {
    visibilityState: "visible",
    addEventListener: () => {},
    removeEventListener: () => {},
  };

  vm.runInNewContext(
    transformed.code,
    {
      exports: exportsObj,
      module: moduleObj,
      require: customRequire,
      process,
      console,
      fetch: mockFetch,
      window: windowStub,
      document: documentStub,
      Date,
      Math,
      Number,
      String,
      Boolean,
      Object,
      Array,
      Map,
      Set,
      Promise,
      Error,
      Symbol,
      AbortController,
      encodeURIComponent,
      setTimeout,
      clearTimeout,
    },
    { filename: fullPath },
  );

  const LiveMarketDashboard = moduleObj.exports.default;

  const renderAndRunEffects = () => {
    hookCursor = 0;
    let tree = LiveMarketDashboard();
    let ranEffect = false;
    for (let i = 0; i < effects.length; i++) {
      if (effects[i]?.changed) {
        ranEffect = true;
        if (typeof cleanups[i] === "function") {
          cleanups[i]();
        }
        cleanups[i] = effects[i].fn();
        effects[i].changed = false;
      }
    }
    if (ranEffect) {
      hookCursor = 0;
      tree = LiveMarketDashboard();
    }
    return tree;
  };

  const findBannerProps = (tree) => {
    const children = Array.isArray(tree.props.children)
      ? tree.props.children
      : [tree.props.children];
    const bannerNode = children.find(
      (c) => c && c.type === "ConnectionStatusBanner",
    );
    return bannerNode.props;
  };

  // 1. Initial mount starts Cycle 1
  let tree = renderAndRunEffects();
  let banner = findBannerProps(tree);
  assert.equal(banner.isRefreshing, true);
  assert.equal(activeFetchResolvers.length, 7); // status + 2*(candles, quote, forming)

  // 2. Manual refresh during active refresh sets pendingRefreshRef without starting overlapping fetches
  banner.onManualRefresh();
  assert.equal(activeFetchResolvers.length, 7); // Still 7 — no overlapping fetch cycle!

  // Resolve Cycle 1 + automatically queued Cycle 2
  await flushActiveFetches();
  tree = renderAndRunEffects();
  banner = findBannerProps(tree);
  assert.equal(banner.isRefreshing, false);
  // Cycle 1 (7 requests) + queued Cycle 2 (7 requests) = 14 total requests
  assert.equal(fetchLog.length, 14);

  // 3. Pure handleToggleAutoRefresh:
  // Toggle ON -> OFF (pauses without triggering fetch)
  const countBeforeToggleOff = fetchLog.length;
  banner.onToggleAutoRefresh();
  tree = renderAndRunEffects();
  banner = findBannerProps(tree);
  assert.equal(banner.autoRefresh, false);
  assert.equal(fetchLog.length, countBeforeToggleOff);

  // Toggle OFF -> ON (enables auto-refresh and triggers refresh outside state updater)
  banner.onToggleAutoRefresh();
  tree = renderAndRunEffects();
  banner = findBannerProps(tree);
  assert.equal(banner.autoRefresh, true);
  assert.equal(banner.isRefreshing, true);
  await flushActiveFetches();
  tree = renderAndRunEffects();
  banner = findBannerProps(tree);
  assert.equal(banner.isRefreshing, false);
  assert.equal(fetchLog.length, countBeforeToggleOff + 7);

  // 4. Switching accessToken during an active refresh aborts token-1 and immediately runs token-2
  banner.onManualRefresh();
  tree = renderAndRunEffects();
  banner = findBannerProps(tree);
  assert.equal(banner.isRefreshing, true);

  // Switch token while token-1 request is still in flight
  currentAuth = { token: "token-2", session: { access_token: "token-2" } };
  tree = renderAndRunEffects();
  banner = findBannerProps(tree);
  assert.equal(banner.isRefreshing, true);

  // Verify token-1 requests were aborted and token-2 requests were started immediately
  assert.equal(
    fetchLog.some((r) => r.authHeader === "Bearer token-1" && r.aborted),
    true,
  );
  assert.equal(
    fetchLog.some((r) => r.authHeader === "Bearer token-2" && !r.aborted),
    true,
  );

  await flushActiveFetches();
  tree = renderAndRunEffects();
  banner = findBannerProps(tree);
  assert.equal(banner.isRefreshing, false);

  // 5. Failed poll marks cached market data as stale and locks signals (no stale data presented as current)
  shouldFailCandles = true;
  banner.onManualRefresh();
  await flushActiveFetches();
  tree = renderAndRunEffects();
  // marketsState is states[2]
  const marketsStateAfterError = states[2];
  assert.equal(marketsStateAfterError.NIFTY50.isStale, true);
  assert.equal(
    marketsStateAfterError.NIFTY50.indicatorDecision.is_current_signal,
    false,
  );
  assert.equal(
    marketsStateAfterError.NIFTY50.marketIntelligence.is_live_actionable,
    false,
  );
  shouldFailCandles = false;

  // 6. Clearing accessToken (logout) during an active refresh immediately resets isRefreshing to false
  banner.onManualRefresh();
  tree = renderAndRunEffects();
  banner = findBannerProps(tree);
  assert.equal(banner.isRefreshing, true);

  currentAuth = { token: null, session: null };
  tree = renderAndRunEffects();
  banner = findBannerProps(tree);
  assert.equal(banner.isRefreshing, false);

  // 7. Unmount cleanup cancels all active work and prevents any further state updates
  for (const cleanup of cleanups) {
    if (typeof cleanup === "function") cleanup();
  }
  await flushActiveFetches();
});


test("Phase 3 Admin Control Center, Login, Account & Auth components compile cleanly, pass ESLint, and enforce IP-independent admin access", () => {
  const authAndAdminFiles = [
    "src/lib/api.ts",
    "src/components/auth/AuthProvider.tsx",
    "src/components/auth/DashboardAccessGate.tsx",
    "src/app/login/page.tsx",
    "src/app/account/page.tsx",
    "src/app/admin/page.tsx",
    "src/components/admin/AdminUsersPanel.tsx",
  ];

  for (const rel of authAndAdminFiles) {
    const fullPath = path.join(webRoot, rel);
    assert.equal(fs.existsSync(fullPath), true, `Expected ${rel} to exist`);
    const source = fs.readFileSync(fullPath, "utf8");
    const result = babel.transformSync(source, {
      filename: fullPath,
      presets: [
        requireWithFallback("@babel/preset-typescript"),
        [requireWithFallback("@babel/preset-react"), { runtime: "automatic" }],
      ],
    });
    assert.ok(result && result.code && result.code.length > 0, `Failed to compile ${rel}`);
  }

  // Verify AuthProvider exposes both token and session.access_token for LiveMarketDashboard compatibility
  const authProviderSrc = fs.readFileSync(path.join(webRoot, "src/components/auth/AuthProvider.tsx"), "utf8");
  assert.match(authProviderSrc, /access_token:\s*token/);

  // Verify LoginPage wraps useSearchParams in a Suspense boundary
  const loginSrc = fs.readFileSync(path.join(webRoot, "src/app/login/page.tsx"), "utf8");
  assert.match(loginSrc, /<Suspense/);

  // Verify AdminPage includes all 6 Admin Control Center sections
  const adminPageSrc = fs.readFileSync(path.join(webRoot, "src/app/admin/page.tsx"), "utf8");
  for (const sectionId of ["overview", "users", "roles", "content", "audit", "health"]) {
    assert.match(adminPageSrc, new RegExp(`"${sectionId}"`));
  }

  // Verify AdminUsersPanel includes Create, Edit, and Delete dialogs and Global IP (*) support
  const usersPanelSrc = fs.readFileSync(path.join(webRoot, "src/components/admin/AdminUsersPanel.tsx"), "utf8");
  assert.match(usersPanelSrc, /create-dialog-title/);
  assert.match(usersPanelSrc, /edit-dialog-title/);
  assert.match(usersPanelSrc, /delete-dialog-title/);
  assert.match(usersPanelSrc, /SUPER ADMIN/);
});
