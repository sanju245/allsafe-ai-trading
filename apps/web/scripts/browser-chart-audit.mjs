import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { readFile } from "node:fs/promises";
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
const fixtureRefresh = "synthetic-browser-chart-audit-refresh-token";
const fixtureCredentials = [fixtureUser.email, fixturePassword, fixtureToken, fixtureRefresh];
const health = { status: "ok", service: "chart-audit-fixture", version: "1", environment: "test" };
const symbols = ["NIFTY50", "BANKNIFTY"];
const fixtureDays = ["2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18"];
const liveWarmupDays = ["2026-11-06", "2026-11-09", "2026-11-11", ...fixtureDays];
const fixtureRequests = [];
const requestErrors = [];
const runtimeErrors = [];
const failedCharts = new Set();
const staleQuotes = new Set();
const rolled = new Set();
let recording;
let signInCount = 0;
let forbiddenAccessCount = 0;

function bars(symbol, days = fixtureDays) {
  const base = symbol === "BANKNIFTY" ? 52000 : 25000;
  return days.flatMap((date, day) =>
    Array.from({ length: date === "2026-11-17" ? 23 : date === "2026-11-18" ? 21 : 25 }, (_, index) => {
      const timestamp = new Date(Date.parse(`${date}T03:45:00Z`) + index * 900000).toISOString();
      const wave = (n) => day * 13 + n * 1.3 + Math.sin((n + day * 6) / 3) * 39;
      const price = base + wave(index), close = base + wave(index + 1);
      return { timestamp, open: price, high: Math.max(price, close) + 4, low: Math.min(price, close) - 6, close, timeframe: "15m", is_forming: false };
    }),
  );
}

function candleFixture(symbol, includeHistory, historyDays) {
  const candles = bars(symbol, liveWarmupDays);
  const current = symbol === "BANKNIFTY" ? "SELL" : "BUY";
  const opposite = current === "BUY" ? "SELL" : "BUY";
  const levels = (side, price) => side === "SELL"
    ? { entry: price, stop_loss: price + 20, target: price - 40 }
    : { entry: price, stop_loss: price - 20, target: price + 40 };
  const events = [
    { timestamp: candles.at(-17).timestamp, decision: opposite, levels: levels(opposite, candles.at(-17).close) },
    { timestamp: candles.at(-1).timestamp, decision: current, levels: levels(current, candles.at(-1).close) },
  ];
  if (rolled.has(symbol)) {
    candles.push(nextBar(candles.at(-1)));
    events.push({ timestamp: candles.at(-1).timestamp, decision: current });
  }
  return {
    candles: historyDays ? candles.filter(c => Date.parse(c.timestamp) >= Date.parse("2026-11-19T00:00:00+05:30") - historyDays * 86400000) : candles,
    timeframe: "15m",
    feed_state: "live",
    is_stale: false,
    checked_at: new Date(Date.parse(candles.at(-1).timestamp) + 902000).toISOString(),
    message: "Synthetic live data for browser audit.",
    indicator_decision: {
      decision: current,
      is_current_signal: true,
      candle_timestamp: candles.at(-1).timestamp,
      reason: "Synthetic confirmed signal.",
      ut_bot_signal: current,
      opening_range_low: candles.at(-3).low,
      opening_range_high: candles.at(-3).high,
      first_breakout: { timestamp: candles.at(-1).timestamp, side: current, decision: current, reason: "Synthetic confirmed signal." },
      ema_bullish: current === "BUY",
      rsi_bullish: current === "BUY",
      macd_bullish: current === "BUY",
      supertrend_bullish: current === "BUY",
      confirmed_candle_count: candles.length,
    },
    indicator_history: includeHistory ? [...events, { timestamp: nextBar(candles.at(-1)).timestamp, decision: opposite }] : undefined,
  };
}

function nextBar(last) {
  return { ...last, timestamp: new Date(Date.parse(last.timestamp) + 900000).toISOString(),
    open: last.close, high: last.close + 9, low: last.close - 4, close: last.close + 7 };
}

async function intercept(route) {
  const request = route.request();
  const { pathname, searchParams, origin: requestOrigin } = new URL(request.url());
  const method = request.method();
  const isSession = pathname === "/api/auth/session" && requestOrigin === origin;
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

  if (isSession && !deployment) return route.continue();
  if (!isSession && !isApi) {
    const forwardsCredential = [request.url(), request.postData() ?? "", ...Object.values(request.headers())]
      .some((value) => fixtureCredentials.some((credential) =>
        value.includes(credential) || value.includes(encodeURIComponent(credential))));
    const appResource = pathname === "/login" || pathname === "/account" || pathname === "/terminal" || pathname === "/favicon.ico" ||
      pathname.startsWith("/_next/") || /^\/chart\/(?:NIFTY50|BANKNIFTY)$/.test(pathname);
    if (forwardsCredential) requestErrors.push(new Error("A browser request tried to forward a fixture credential."));
    if (!forwardsCredential && requestOrigin === origin && appResource && ["GET", "HEAD"].includes(method)) {
      return route.continue();
    }
    return route.abort("blockedbyclient");
  }

  try {
    if (method === "OPTIONS") return respond({});
    if (isSession) {
      const headers = { "cache-control": "no-store" };
      if (method === "DELETE") {
        headers["set-cookie"] = "allsafe_refresh=; Path=/api/auth/session; HttpOnly; Secure; SameSite=Strict; Max-Age=0";
        return route.fulfill({ status: 204, headers });
      }
      if (method === "PUT") {
        assert.deepEqual(request.postDataJSON(), { email: fixtureUser.email, password: fixturePassword });
        signInCount += 1;
        headers["set-cookie"] = `allsafe_refresh=${fixtureRefresh}; Path=/api/auth/session; HttpOnly; Secure; SameSite=Strict`;
      } else {
        assert.equal(method, "POST");
        if (!(await request.headerValue("cookie"))?.includes(fixtureRefresh)) return respond({}, 401);
      }
      return route.fulfill({ status: 200, headers, json: { access_token: fixtureToken, user: fixtureUser, expires_in: 3600 } });
    }
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
      providers: ["groww", "upstox"].map((id) => ({ id, label: id === "groww" ? "Groww" : "Upstox", configured: true, feed_state: id === "groww" ? "failed" : "live", connected: id === "upstox", message: "Fixture" })),
    });
    assert.ok(symbols.includes(symbol), `Expected a supported index for ${pathname}.`);
    if (pathname === "/api/v1/live/candles") {
      assert.equal(searchParams.get("timeframe"), "15m");
      if (includeHistory && failedCharts.has(symbol)) return respond({ detail: "Simulated refresh outage." }, 503);
      if (recording && includeHistory && provider === "upstox") return respond(recording[symbol]);
      return respond(candleFixture(symbol, includeHistory, Number(searchParams.get("history_days"))));
    }
    if (pathname === "/api/v1/live/quote") {
      if (recording && provider === "upstox" && searchParams.has("include_forming")) return respond({
        available: false, feed_state: "closed", is_stale: false, checked_at: recording[symbol].checked_at, quote: null, forming_candle: null,
      });
      const snapshot = candleFixture(symbol, false);
      const forming = nextBar(snapshot.candles.at(-1));
      const stale = staleQuotes.has(symbol);
      return respond({ available: true, feed_state: stale ? "stale" : "live", is_stale: stale, checked_at: snapshot.checked_at,
        quote: { ltp: forming.close, timestamp: snapshot.checked_at },
        forming_candle: searchParams.get("include_forming") ? { ...forming, is_forming: true, is_confirmed: false } : null });
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
  await chart.getByRole("region", { name: "Interactive 15-minute Heikin Ashi chart" }).waitFor();
  for (const side of ["Buy", "Sell"]) await chart.locator(`[aria-label^="${side} signal on"]`).first().waitFor();
  await chart.getByText("Signal confirmation checks", { exact: true }).waitFor();
  assert.equal(await chart.locator(".chart-badge").count(), 2, "Only confirmed events have badges.");
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
  await entry.waitForFunction(() => document.querySelector("#market-data-provider")?.value === "upstox");
  await live.getByRole("img", { name: "NIFTY 50 15-minute candlestick chart" }).waitFor();
  await live.getByRole("img", { name: "BANK NIFTY 15-minute candlestick chart" }).waitFor();
  const history = entry.getByRole("region", { name: "Historical index charts" });
  await history.getByRole("img", { name: "NIFTY 50 Upstox 15-minute historical candlestick chart" }).waitFor();

  const nifty = await openChart(context, live.getByRole("link", { name: /^NIFTY 50/ }), "NIFTY50");
  await assertFullChart(nifty, "NIFTY 50");
  const bank = await openChart(context, live.getByRole("link", { name: /^BANK NIFTY/ }), "BANKNIFTY");
  await assertFullChart(bank, "BANK NIFTY");
  assert.equal(signInCount, 1, "Both chart tabs should reuse one sign-in.");
  await bank.getByRole("region", { name: "Signal price levels" }).getByText("Stop-loss", { exact: true }).waitFor();
  await bank.getByText("Signal confirmation checks", { exact: true }).click();
  await bank.getByText(/First breakout · SELL/).waitFor();
  await bank.reload();
  await assertFullChart(bank, "BANK NIFTY");
  assert.equal(signInCount, 1, "Reload should restore the session without a second login.");
  for (const symbol of symbols) {
    assert.ok(fixtureRequests.some((item) => item.symbol === symbol && item.includeHistory));
  }
  await nifty.bringToFront();
  const plot = nifty.locator(".chart-plot");
  const initialSize = Number(await plot.getAttribute("data-range-size"));
  const badge = nifty.locator('.chart-badge.buy');
  const originalBadgeX = await badge.evaluate(el => el.getBoundingClientRect().x);
  const box = await plot.boundingBox();
  assert.ok(box && box.width > 300 && box.height > 250);
  await nifty.getByRole("button", { name: "Zoom in" }).click();
  await nifty.waitForFunction((size) => Number(document.querySelector(".chart-plot").dataset.rangeSize) < size, initialSize);
  await nifty.mouse.move(box.x + box.width * .45, box.y + box.height * .55);
  await nifty.mouse.down();
  await nifty.mouse.move(box.x + box.width * .58, box.y + box.height * .55, { steps: 6 });
  await nifty.mouse.up();
  await nifty.waitForFunction(x => Math.abs(document.querySelector(".chart-badge.buy").getBoundingClientRect().x - x) > 3, originalBadgeX);
  await nifty.getByRole("button", { name: "Fit", exact: true }).click();
  await nifty.getByRole("button", { name: "Latest", exact: true }).click();
  await nifty.getByRole("button", { name: "Signals", exact: true }).click();
  assert.equal(await nifty.locator(".chart-badge").count(), 0);
  await nifty.getByRole("button", { name: "Signals", exact: true }).click();
  await assertFullChart(nifty, "NIFTY 50");
  await nifty.getByRole("button", { name: "Full screen", exact: true }).click();
  await nifty.getByRole("button", { name: "Exit full screen" }).click();
  await nifty.setViewportSize({ width: 390, height: 844 });
  await nifty.getByRole("button", { name: "Fit", exact: true }).click();
  await assertFullChart(nifty, "NIFTY 50");
  assert.ok(await nifty.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await nifty.setViewportSize({ width: 1280, height: 800 });
  await nifty.getByRole("button", { name: "Fit", exact: true }).click();
  if (process.env.CHART_AUDIT_SCREENSHOT && !process.env.CHART_AUDIT_REPLAY) await nifty.screenshot({ path: process.env.CHART_AUDIT_SCREENSHOT, fullPage: true });

  const historyRequest = context.waitForEvent("request", {
    predicate(request) {
      const url = new URL(request.url());
      return url.pathname === "/api/v1/live/candles" && url.searchParams.get("symbol") === "NIFTY50" &&
        url.searchParams.get("history_days") === "7" && new URL(request.frame().url()).pathname === "/chart/NIFTY50";
    },
  });
  const historical = await openChart(context, history.getByRole("link", { name: /^NIFTY 50/ }), "NIFTY50");
  await historyRequest;
  await historical.getByRole("heading", { name: "NIFTY 50", exact: true }).waitFor();
  assert.equal(new URL(historical.url()).searchParams.get("days"), "7");
  assert.equal(await historical.getByRole("combobox", { name: "History" }).inputValue(), "7");
  const provider = historical.getByRole("combobox", { name: "Market data" });
  await historical.waitForFunction(() => document.querySelector("#chart-provider")?.value === "upstox");
  await assertFullChart(historical, "NIFTY 50");
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
  staleQuotes.add("NIFTY50");
  await nifty.getByText("Feed delayed", { exact: true }).waitFor();
  assert.equal(await plot.getAttribute("data-forming"), "false");
  assert.equal(await nifty.getByText("Current confirmed signal", { exact: true }).count(), 0);
  assert.equal(await nifty.locator(".chart-badge").count(), 2);
  staleQuotes.delete("NIFTY50");
  const oldCount = Number(await plot.getAttribute("data-closed-bars"));
  rolled.add("NIFTY50");
  await nifty.waitForFunction(n => Number(document.querySelector(".chart-plot").dataset.closedBars) === n + 1, oldCount);
  await nifty.getByText("Current confirmed signal", { exact: true }).waitFor();
  assert.equal(await nifty.locator(".chart-badge").count(), 3, "The new close preserves the preceding signals.");
  failedCharts.add("NIFTY50");
  await nifty.getByRole("alert").filter({ hasText: /503|unavailable|refresh|load/i }).waitFor({ timeout: 35000 });
  assert.equal(await nifty.getByText("Current confirmed signal", { exact: true }).count(), 0);
  failedCharts.delete("NIFTY50");

  if (process.env.CHART_AUDIT_REPLAY) {
    recording = JSON.parse(await readFile(process.env.CHART_AUDIT_REPLAY, "utf8"));
    for (const [index, page] of [nifty, bank].entries()) {
      const expected = recording[symbols[index]];
      await page.bringToFront();
      await page.getByRole("combobox", { name: "Market data" }).selectOption("upstox");
      await page.evaluate(() => window.dispatchEvent(new Event("online")));
      await page.getByText("Market closed", { exact: true }).waitFor();
      await page.waitForFunction(n => Number(document.querySelector(".chart-plot")?.dataset.closedBars) === n, expected.candles.length);
      await page.getByRole("button", { name: "Fit", exact: true }).click();
      assert.equal(await page.locator(".chart-badge").count(), expected.indicator_history.length);
      for (const p of expected.indicator_history) {
        const mark = page.locator(`.chart-badge[data-time="${Date.parse(p.timestamp) / 1000}"][data-side="${p.decision}"]`);
        await mark.waitFor();
        await mark.hover({ force: true });
        const name = await mark.getAttribute("aria-label");
        await page.locator(".chart-values").getByText(name.split("signal on ")[1], { exact: true }).waitFor();
      }
      assert.equal(await page.getByText("Current confirmed signal", { exact: true }).count(), 0);
      if (!index && process.env.CHART_AUDIT_SCREENSHOT) {
        await page.mouse.move(1, 1);
        await page.screenshot({ path: process.env.CHART_AUDIT_SCREENSHOT, fullPage: true });
      }
    }
    console.log("PASS: actual recorded broker candles, badge timestamps, crosshair alignment and closed-market status for both indices.");
  }

  const hasStoredToken = await nifty.evaluate((token) => [localStorage, sessionStorage].some((storage) =>
    Object.values(storage).some((value) => value.includes(token))), fixtureToken);
  assert.equal(hasStoredToken, false);
  assert.ok(!nifty.url().includes(fixtureToken));
  assert.ok(!(await context.cookies()).some((cookie) => cookie.value.includes(fixtureToken)));
  assert.ok((await context.cookies()).some((cookie) => cookie.value === fixtureRefresh && cookie.httpOnly));
  assert.ok(!nifty.url().includes("#session="));

  await entry.getByRole("button", { name: "Sign out" }).click();
  for (const chart of [nifty, bank, historical]) {
    await chart.getByRole("heading", { name: "Sign in to use AllSafe" }).waitFor();
  }
  assert.equal(forbiddenAccessCount, 0, "The frontend should wait for authorization before fetching protected data.");
  assert.deepEqual(requestErrors, []);
  assert.deepEqual(runtimeErrors, []);
  console.log("PASS: sign-in, both chart tabs, Heikin Ashi, confirmed markers, zoom, drag, fit, fullscreen, mobile, provider switch, stale feed, close rollover, refresh failure and sign-out.");
}

let server;
let nextServer;
let browser;
try {
  if (!deployment) {
    server = createServer(async (request, response) => {
      const url = new URL(request.url, fixtureApi);
      const reply = (status, data) => {
        response.writeHead(status, { "content-type": "application/json" });
        response.end(JSON.stringify(data));
      };
      if (url.pathname === "/health") return reply(200, health);
      if (url.pathname === "/auth/v1/logout") return reply(200, {});
      if (url.pathname !== "/auth/v1/token") return reply(404, {});
      try {
        const chunks = [];
        for await (const chunk of request) chunks.push(chunk);
        const body = JSON.parse(Buffer.concat(chunks));
        if (url.searchParams.get("grant_type") === "password") {
          assert.deepEqual(body, { email: fixtureUser.email, password: fixturePassword });
          signInCount += 1;
        } else {
          assert.deepEqual(body, { refresh_token: fixtureRefresh });
        }
        return reply(200, { access_token: fixtureToken, refresh_token: fixtureRefresh, expires_in: 3600, user: fixtureUser });
      } catch (error) {
        requestErrors.push(error);
        return reply(400, {});
      }
    });
    server.listen(3906, "127.0.0.1");
    await once(server, "listening");
    const env = {
      ...process.env,
      API_BASE_URL: fixtureApi,
      NEXT_PUBLIC_API_BASE_URL: fixtureApi,
      NEXT_PUBLIC_SUPABASE_URL: fixtureApi,
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
