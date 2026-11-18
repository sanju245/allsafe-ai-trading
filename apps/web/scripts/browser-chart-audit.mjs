import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";

// Run from the repository root with Chrome installed:
// npm install --prefix .browser-audit-tool --no-audit --no-fund playwright@1.65.1
// node apps/web/scripts/browser-chart-audit.mjs
// To audit the public release build, add --deployment https://allsafe-ai-trading.vercel.app
const toolRequire = createRequire(new URL("../../../.browser-audit-tool/package.json", import.meta.url));
const { chromium } = toolRequire("playwright");
const webRoot = fileURLToPath(new URL("../", import.meta.url));
const next = createRequire(import.meta.url).resolve("next/dist/bin/next");
const args = process.argv.slice(2);
const deployment = args.length === 2 && args[0] === "--deployment" ? args[1] : null;
const publicOrigin = "https://allsafe-ai-trading.vercel.app";
assert.ok(args.length === 0 || deployment === publicOrigin, `Use --deployment ${publicOrigin} to audit production.`);

const localOrigin = "http://127.0.0.1:3905";
const fixtureApi = "http://127.0.0.1:3906";
const origin = deployment ?? localOrigin;
const fixtureUser = { id: "browser-chart-audit-user", email: "browser-chart-audit@example.test" };
const fixturePassword = "synthetic-browser-chart-audit";
const fixtureToken = "synthetic-browser-chart-audit-access-token";
const fixtureCredentials = [fixtureUser.email, fixturePassword, fixtureToken];
const health = { status: "ok", service: "chart-audit-fixture", version: "1", environment: "test" };
const symbols = ["NIFTY50", "BANKNIFTY"];
const fixtureDays = ["2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17"];
const fixtureRequests = [];
const requestErrors = [];
const runtimeErrors = [];
const failedCharts = new Set();
let signInCount = 0;
let forbiddenAccessCount = 0;

function bars(symbol) {
  const base = symbol === "BANKNIFTY" ? 52000 : 25000;
  return fixtureDays.flatMap((date, day) =>
    Array.from({ length: day === 3 ? 23 : 25 }, (_, index) => {
      const timestamp = new Date(Date.parse(`${date}T03:45:00Z`) + index * 900000).toISOString();
      const price = base + day * 13 + index * 4;
      return { timestamp, open: price, high: price + 9, low: price - 6, close: price + 2, timeframe: "15m", is_forming: false };
    }),
  );
}

function candleFixture(symbol, includeHistory) {
  const candles = bars(symbol);
  const current = symbol === "BANKNIFTY" ? "SELL" : "BUY";
  const opposite = current === "BUY" ? "SELL" : "BUY";
  return {
    candles,
    timeframe: "15m",
    feed_state: "live",
    is_stale: false,
    message: "Synthetic live data for browser audit.",
    indicator_decision: {
      decision: current,
      is_current_signal: true,
      candle_timestamp: candles.at(-1).timestamp,
      reason: "Synthetic confirmed signal.",
      ut_bot_signal: current,
      ema_bullish: current === "BUY",
      rsi_bullish: current === "BUY",
      macd_bullish: current === "BUY",
      supertrend_bullish: current === "BUY",
      confirmed_candle_count: candles.length,
    },
    indicator_history: includeHistory ? [
      { timestamp: candles.at(-4).timestamp, decision: opposite },
      { timestamp: candles.at(-1).timestamp, decision: current },
    ] : undefined,
  };
}

async function intercept(route) {
  const request = route.request();
  const { pathname, searchParams, origin: requestOrigin } = new URL(request.url());
  const method = request.method();
  const isAuth = /\/auth\/v1\/(?:token|logout)$/.test(pathname);
  const isApi = pathname.startsWith("/api/v1/") || pathname === "/health";
  const respond = (json, status = 200) => route.fulfill({
    status,
    json,
    headers: {
      "access-control-allow-origin": origin,
      "access-control-allow-headers": "authorization, apikey, content-type, accept",
      "access-control-allow-methods": "GET, POST, OPTIONS",
      "cache-control": "no-store",
    },
  });

  if (!isAuth && !isApi) {
    const forwardsCredential = [request.url(), request.postData() ?? "", ...Object.values(request.headers())]
      .some((value) => fixtureCredentials.some((credential) =>
        value.includes(credential) || value.includes(encodeURIComponent(credential))));
    const appResource = pathname === "/login" || pathname === "/terminal" || pathname === "/favicon.ico" ||
      pathname.startsWith("/_next/") || /^\/chart\/(?:NIFTY50|BANKNIFTY)$/.test(pathname);
    if (forwardsCredential) requestErrors.push(new Error("A browser request tried to forward a fixture credential."));
    if (!forwardsCredential && requestOrigin === origin && appResource && ["GET", "HEAD"].includes(method)) {
      return route.continue();
    }
    return route.abort("blockedbyclient");
  }

  try {
    if (method === "OPTIONS") return respond({});
    if (pathname.endsWith("/auth/v1/token")) {
      assert.equal(method, "POST");
      assert.deepEqual(request.postDataJSON(), { email: fixtureUser.email, password: fixturePassword });
      signInCount += 1;
      return respond({ access_token: fixtureToken, user: fixtureUser });
    }
    if (pathname.endsWith("/auth/v1/logout")) return respond({});
    if (pathname === "/health") return respond(health);
    if (request.headers().authorization !== `Bearer ${fixtureToken}`) {
      forbiddenAccessCount += 1;
      return respond({ detail: "Sign in required." }, 401);
    }

    const symbol = searchParams.get("symbol");
    const provider = searchParams.get("provider");
    const includeHistory = searchParams.get("include_indicator_history") === "true";
    fixtureRequests.push({ pathname, symbol, provider, includeHistory });

    if (pathname === "/api/v1/auth/me") return respond({ profile: { ...fixtureUser, role: "user", status: "active" } });
    if (pathname === "/api/v1/live/status") return respond({
      feed_state: "live", provider, streaming_enabled: true, connected: true, session_open: true,
      last_error: null, instruments: Object.fromEntries(symbols.map((id) => [id, { feed_state: "live" }])),
    });
    if (pathname === "/api/v1/live/providers") return respond({
      providers: ["groww", "upstox"].map((id) => ({ id, label: id === "groww" ? "Groww" : "Upstox", configured: true, feed_state: "live", connected: true, message: "Fixture" })),
    });
    assert.ok(symbols.includes(symbol), `Expected a supported index for ${pathname}.`);
    if (pathname === "/api/v1/live/candles") {
      assert.equal(searchParams.get("timeframe"), "15m");
      if (includeHistory && failedCharts.has(symbol)) return respond({ detail: "Simulated refresh outage." }, 503);
      return respond(candleFixture(symbol, includeHistory));
    }
    if (pathname === "/api/v1/live/quote") {
      const last = bars(symbol).at(-1);
      return respond({ available: true, feed_state: "live", is_stale: false, quote: { ltp: last.close, timestamp: last.timestamp } });
    }
    if (pathname === "/api/v1/live/forming-candle") return respond({ available: false, forming_candle: null });
    if (pathname === "/api/v1/market-data/upstox/candles") {
      const candles = bars(symbol);
      return respond({ candles, provider: "upstox", timeframe: "15m", instrument: symbol, start_date: fixtureDays[0], end_date: fixtureDays.at(-1), retrieved_at: candles.at(-1).timestamp, last_candle_at: candles.at(-1).timestamp, message: "Synthetic Upstox history." });
    }
    throw new Error(`Unhandled fixture endpoint ${pathname}`);
  } catch (error) {
    requestErrors.push(error);
    return respond({ detail: "Test fixture rejected this request." }, 500);
  }
}

async function waitForServer(child) {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Next.js exited with code ${child.exitCode}.`);
    try {
      if ((await fetch(`${localOrigin}/login`, { signal: AbortSignal.timeout(750) })).ok) return;
    } catch {
      // Wait for the local production server to accept requests.
    }
    await delay(300);
  }
  throw new Error("Local Next.js production server did not become ready.");
}

async function openChart(context, link, symbol) {
  const [chart] = await Promise.all([context.waitForEvent("page"), link.click()]);
  await chart.waitForURL((url) => url.origin === origin && url.pathname === `/chart/${symbol}`);
  chart.on("pageerror", (error) => runtimeErrors.push(error));
  assert.equal(await chart.evaluate(() => window.opener === null), true);
  return chart;
}

async function assertFullChart(chart, title) {
  await chart.getByRole("heading", { name: title, exact: true }).waitFor();
  await chart.getByRole("img", { name: /^15-minute candlestick chart with \d+ bars$/ }).waitFor();
  await chart.locator('svg [aria-label^="BUY signal on"]').first().waitFor();
  await chart.locator('svg [aria-label^="SELL signal on"]').first().waitFor();
  await chart.getByRole("heading", { name: "Indicator readings" }).waitFor();
}

async function audit(context) {
  await context.route("**/*", intercept);
  const signedOut = await context.newPage();
  const chartDestination = "/chart/BANKNIFTY?provider=upstox&days=7";
  await signedOut.goto(chartDestination);
  const signInLink = await signedOut.getByRole("link", { name: "Go to sign in" }).getAttribute("href");
  assert.ok(signInLink);
  assert.equal(new URL(signInLink, origin).searchParams.get("next"), chartDestination);
  await signedOut.close();

  const entry = await context.newPage();
  entry.on("pageerror", (error) => runtimeErrors.push(error));
  const response = await entry.goto("/login");
  assert.ok(response?.ok(), "The login page must be publicly reachable.");
  await entry.getByLabel("Email").fill(fixtureUser.email);
  await entry.getByLabel("Password").fill(fixturePassword);
  await entry.getByRole("button", { name: "Sign in", exact: true }).click();
  await entry.waitForURL("**/terminal");
  const live = entry.getByRole("region", { name: "Live index charts" });
  await live.getByRole("img", { name: "NIFTY 50 15-minute candlestick chart" }).waitFor();
  await live.getByRole("img", { name: "BANK NIFTY 15-minute candlestick chart" }).waitFor();
  const history = entry.getByRole("region", { name: "Historical index charts" });
  await history.getByRole("img", { name: "NIFTY 50 Upstox 15-minute historical candlestick chart" }).waitFor();

  const nifty = await openChart(context, live.getByRole("link", { name: /^NIFTY 50/ }), "NIFTY50");
  await assertFullChart(nifty, "NIFTY 50");
  const bank = await openChart(context, live.getByRole("link", { name: /^BANK NIFTY/ }), "BANKNIFTY");
  await assertFullChart(bank, "BANK NIFTY");
  assert.equal(signInCount, 1, "Both chart tabs should reuse one sign-in.");
  for (const symbol of symbols) {
    assert.ok(fixtureRequests.some((item) => item.symbol === symbol && item.includeHistory));
  }
  await nifty.getByRole("button", { name: "Zoom in" }).click();
  await nifty.getByRole("img", { name: "15-minute candlestick chart with 60 bars" }).waitFor();

  const historyRequest = context.waitForEvent("request", {
    predicate(request) {
      const url = new URL(request.url());
      return url.pathname === "/api/v1/market-data/upstox/candles" && url.searchParams.get("symbol") === "NIFTY50" &&
        url.searchParams.get("days") === "7" && new URL(request.frame().url()).pathname === "/chart/NIFTY50";
    },
  });
  const historical = await openChart(context, history.getByRole("link", { name: /^NIFTY 50/ }), "NIFTY50");
  await historyRequest;
  await historical.getByRole("heading", { name: "NIFTY 50", exact: true }).waitFor();
  assert.equal(new URL(historical.url()).searchParams.get("days"), "7");
  await historical.getByText("Upstox history · Last 7 days").waitFor();
  const provider = historical.getByRole("combobox", { name: "Market data" });
  await historical.waitForFunction(() => document.querySelector("#chart-provider")?.value === "upstox");
  await historical.getByRole("img", { name: /^15-minute candlestick chart with \d+ bars$/ }).waitFor();
  const switched = historical.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === "/api/v1/live/candles" && url.searchParams.get("provider") === "groww";
  });
  await provider.selectOption("groww");
  await switched;
  assert.equal(await provider.inputValue(), "groww");
  assert.equal(new URL(historical.url()).searchParams.get("days"), null);

  await assertFullChart(nifty, "NIFTY 50");
  await nifty.getByText("Current confirmed signal", { exact: true }).waitFor();
  await nifty.bringToFront();
  failedCharts.add("NIFTY50");
  await nifty.getByRole("alert").filter({ hasText: /503|unavailable|refresh|load/i }).waitFor({ timeout: 35000 });
  assert.equal(await nifty.getByText("Current confirmed signal", { exact: true }).count(), 0);
  failedCharts.delete("NIFTY50");

  const hasStoredToken = await nifty.evaluate((token) => [localStorage, sessionStorage].some((storage) =>
    Object.values(storage).some((value) => value.includes(token))), fixtureToken);
  assert.equal(hasStoredToken, false);
  assert.ok(!nifty.url().includes(fixtureToken));
  assert.ok(!(await context.cookies()).some((cookie) => cookie.value.includes(fixtureToken)));

  await entry.getByRole("button", { name: "Sign out" }).click();
  for (const chart of [nifty, bank, historical]) {
    await chart.getByRole("heading", { name: "Sign in to use AllSafe" }).waitFor();
  }
  assert.equal(forbiddenAccessCount, 0, "The frontend should wait for authorization before fetching protected data.");
  assert.deepEqual(requestErrors, []);
  assert.deepEqual(runtimeErrors, []);
  console.log("PASS: one sign-in, both new chart tabs, 15-minute candles, BUY and SELL markers, zoom, provider switch, refresh failure, and sign-out across tabs.");
}

let server;
let nextServer;
let browser;
try {
  if (!deployment) {
    server = createServer((request, response) => {
      response.writeHead(request.url === "/health" ? 200 : 404, { "content-type": "application/json" });
      response.end(JSON.stringify(health));
    });
    server.listen(3906, "127.0.0.1");
    await once(server, "listening");
    const env = {
      ...process.env,
      API_BASE_URL: fixtureApi,
      NEXT_PUBLIC_API_BASE_URL: fixtureApi,
      NEXT_PUBLIC_SUPABASE_URL: localOrigin,
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "synthetic-public-anon-key",
      NEXT_TELEMETRY_DISABLED: "1",
    };
    const build = spawn(process.execPath, [next, "build"], { cwd: webRoot, env, stdio: "inherit" });
    const [buildCode] = await once(build, "exit");
    assert.equal(buildCode, 0, "The local production build must succeed.");
    nextServer = spawn(process.execPath, [next, "start", "--hostname", "127.0.0.1", "--port", "3905"], { cwd: webRoot, env, stdio: "inherit" });
    await waitForServer(nextServer);
  }
  browser = await chromium.launch({ channel: "chrome", headless: true });
  const context = await browser.newContext({ baseURL: origin, serviceWorkers: "block" });
  context.setDefaultTimeout(15000);
  await audit(context);
} finally {
  if (browser) await browser.close();
  if (nextServer) nextServer.kill();
  if (server) server.close();
}
