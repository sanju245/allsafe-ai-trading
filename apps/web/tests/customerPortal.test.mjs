import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import test from "node:test";
import vm from "node:vm";
import { BroadcastChannel } from "node:worker_threads";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const userId = "00000000-0000-4000-8000-000000000001";
const authReply = { access_token: "test-token", user: { id: userId, email: "customer@example.com" } };
const activeProfile = {
  id: userId, email: "customer@example.com", role: "user", status: "active",
};
const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { "Content-Type": "application/json" },
});

class TestBroadcastChannel extends BroadcastChannel {
  constructor(name) {
    super(name);
    this.unref();
  }
}

function compile(relativePath) {
  const fullPath = path.join(webRoot, relativePath);
  const output = ts.transpileModule(fs.readFileSync(fullPath, "utf8"), {
    fileName: fullPath, reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  });
  assert.equal(output.diagnostics?.length ?? 0, 0);
  return output.outputText;
}

function authHarness(fetchImpl, href = "https://site.example.test/") {
  const slots = [];
  let cursor = 0;
  let effect;
  const calls = [];
  const timeouts = [];
  const location = new URL(href);
  const history = {
    state: { existing: true },
    replaceState(state, title, url) {
      assert.strictEqual(state, this.state);
      location.href = new URL(url, location).href;
    },
  };
  const hooks = {
    createContext: () => ({ Provider: "AuthContextProvider" }),
    useState: (initial) => {
      const slot = cursor++;
      if (!(slot in slots)) slots[slot] = initial;
      return [slots[slot], (value) => { slots[slot] = typeof value === "function" ? value(slots[slot]) : value; }];
    },
    useRef: (initial) => {
      const slot = cursor++;
      if (!(slot in slots)) slots[slot] = { current: initial };
      return slots[slot];
    },
    useMemo: (callback) => callback(),
    useCallback: (callback) => callback,
    useEffect: (callback) => { effect = callback; },
  };
  const moduleObj = { exports: {} };
  vm.runInNewContext(compile("src/components/auth/AuthProvider.tsx"), {
    module: moduleObj, exports: moduleObj.exports,
    require: (name) => {
      if (name === "react") return hooks;
      if (name === "react/jsx-runtime") return { jsx: (type, props) => ({ type, props }) };
      throw new Error("Unexpected import: " + name);
    },
    process: { env: {
      NEXT_PUBLIC_SUPABASE_URL: "https://auth.example.test",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "test-anon-key",
      NEXT_PUBLIC_API_BASE_URL: "https://api.example.test",
    } },
    AbortSignal: {
      timeout: (milliseconds) => {
        timeouts.push(milliseconds);
        return AbortSignal.timeout(milliseconds);
      },
    },
    console, crypto: webcrypto, BroadcastChannel: TestBroadcastChannel,
    window: { location, history, setTimeout, clearTimeout },
    fetch: async (url, options) => {
      calls.push({ url, options });
      return fetchImpl(url, options);
    },
  });
  const context = () => {
    cursor = 0;
    return moduleObj.exports.AuthProvider({ children: null }).props.value;
  };
  return {
    calls, timeouts, context, location,
    mount(t) {
      context();
      t.after(effect());
    },
    chartSessionFragment: moduleObj.exports.chartSessionFragment,
  };
}

async function waitForAuth(condition) {
  for (let attempt = 0; attempt < 200; attempt++) {
    if (condition()) return;
    await delay(10);
  }
  assert.fail("Timed out waiting for the auth state");
}

test("sign-in establishes only the API-verified profile for the authenticated subject and bounds requests", async () => {
  const harness = authHarness(async (url) => url.includes("/token?") ? json(authReply) : json(activeProfile));
  await harness.context().signIn(" customer@example.com ", "password-123");
  assert.equal(harness.context().session.user.id, userId);
  assert.equal(harness.context().profile.id, userId);
  assert.equal(harness.context().loading, false);
  assert.equal(JSON.parse(harness.calls[0].options.body).email, "customer@example.com");
  assert.deepEqual(harness.timeouts, [12000, 65000, 5000]);
  assert.ok(harness.calls.some(({ url }) => url.endsWith("/api/v1/auth/login-events")));
  for (const { options } of harness.calls) {
    assert.equal(options.credentials, "omit");
    assert.ok(options.signal instanceof AbortSignal);
  }
});

test("customer sign-in remains successful when login IP audit storage is unavailable", async () => {
  const harness = authHarness(async (url) => {
    if (url.includes("/token?")) return json(authReply);
    if (url.endsWith("/api/v1/auth/login-events")) throw new Error("audit service unavailable");
    return json(activeProfile);
  });

  await harness.context().signIn("customer@example.com", "password-123");
  await delay(0);

  assert.equal(harness.context().session.user.id, userId);
  assert.ok(harness.calls.some(({ url }) => url.endsWith("/api/v1/auth/login-events")));
});

test("a different profile subject cannot establish a signed-in customer session", async () => {
  const harness = authHarness(async (url) => {
    if (url.includes("/token?")) return json(authReply);
    if (url.includes("/logout")) return new Response(null, { status: 204 });
    return json({ ...activeProfile, id: "00000000-0000-4000-8000-000000000002" });
  });
  await assert.rejects(harness.context().signIn("customer@example.com", "password-123"), /unexpected profile/);
  assert.equal(harness.context().session, null);
  assert.equal(harness.context().profile, null);
  assert.ok(harness.calls.some(({ url }) => url.endsWith("/logout")));
});

test("customer profile establishes a session without IP fields", async () => {
  const harness = authHarness(async (url) => url.includes("/token?") ? json(authReply) : json(activeProfile));
  await harness.context().signIn("customer@example.com", "password-123");
  assert.equal(harness.context().session.user.id, userId);
  assert.equal(harness.context().profile.id, userId);
  assert.equal("allowed_ip" in harness.context().profile, false);
  assert.equal("client_ip" in harness.context().profile, false);
});

test("a profile startup timeout explains the wait and leaves the portal signed out", async () => {
  const harness = authHarness(async (url) => {
    if (url.includes("/token?")) return json(authReply);
    if (url.includes("/logout")) return new Response(null, { status: 204 });
    throw { name: "TimeoutError" };
  });
  await assert.rejects(harness.context().signIn("customer@example.com", "password-123"), /taking longer than usual to start/);
  assert.equal(harness.context().session, null);
  assert.equal(harness.context().profile, null);
  assert.equal(harness.context().loading, false);
});

test("sign-out clears local credentials immediately even if upstream logout never responds", async () => {
  const harness = authHarness(async (url) => {
    if (url.includes("/logout")) return new Promise(() => {});
    return url.includes("/token?") ? json(authReply) : json(activeProfile);
  });
  await harness.context().signIn("customer@example.com", "password-123");
  await harness.context().signOut();
  assert.equal(harness.context().session, null);
  assert.equal(harness.context().profile, null);
  assert.equal(harness.context().loading, false);
});

test("a sign-in response arriving after sign-out cannot restore the session", async () => {
  let finishProfile;
  const harness = authHarness(async (url) => {
    if (url.includes("/token?")) return json(authReply);
    if (url.includes("/logout")) return new Response(null, { status: 204 });
    return new Promise((resolve) => { finishProfile = resolve; });
  });
  const pending = harness.context().signIn("customer@example.com", "password-123");
  while (!finishProfile) await new Promise((resolve) => setImmediate(resolve));
  await harness.context().signOut();
  finishProfile(json(activeProfile));
  await assert.rejects(pending, /cancelled/);
  assert.equal(harness.context().session, null);
  assert.equal(harness.context().profile, null);
});

test("a denied password operation clears a stale session and obeys the API password bound", async () => {
  const harness = authHarness(async (url) => {
    if (url.includes("/token?")) return json(authReply);
    if (url.includes("/logout")) return new Response(null, { status: 204 });
    if (url.includes("/password")) return json({ detail: { code: "account_paused" } }, 403);
    return json(activeProfile);
  });
  await harness.context().signIn("customer@example.com", "password-123");
  await assert.rejects(harness.context().changePassword("x".repeat(129)), /between 8 and 128/);
  assert.ok(!harness.calls.some(({ url }) => url.endsWith("/password")));
  await assert.rejects(harness.context().changePassword("new-password-123"), /paused/);
  assert.equal(harness.context().session, null);
  assert.equal(harness.context().profile, null);
});

test("temporary profile outage preserves a valid session, but expired authentication removes it", async () => {
  let profileStatus = 200;
  const harness = authHarness(async (url) => {
    if (url.includes("/token?")) return json(authReply);
    if (url.includes("/logout")) return new Response(null, { status: 204 });
    return profileStatus === 200 ? json(activeProfile) : json({ detail: "unavailable" }, profileStatus);
  });
  await harness.context().signIn("customer@example.com", "password-123");
  profileStatus = 503;
  await assert.rejects(harness.context().refreshProfile(), /temporarily unavailable/);
  assert.equal(harness.context().session.user.id, userId);
  profileStatus = 401;
  await assert.rejects(harness.context().refreshProfile(), /expired/);
  assert.equal(harness.context().session, null);
  assert.equal(harness.context().profile, null);
  assert.equal(harness.context().loading, false);
});

test("active admin profiles are verified without IP metadata", async () => {
  const harness = authHarness(async (url) => url.includes("/token?") ? json(authReply) : json({
    ...activeProfile, role: "admin",
  }));
  await harness.context().signIn("admin@example.com", "password-123");
  assert.equal(harness.context().profile.role, "admin");
  assert.equal("allowed_ip" in harness.context().profile, false);
  assert.ok(!harness.calls.some(({ url }) => url.endsWith("/api/v1/auth/login-events")));
});

test("a chart tab receives only its invited session and verifies the profile with the API", async (t) => {
  const source = authHarness(async (url) => url.includes("/token?") ? json(authReply) : json(activeProfile));
  const otherId = "00000000-0000-4000-8000-000000000002";
  const otherUser = { id: otherId, email: "other@example.com" };
  const other = authHarness(async (url) => url.includes("/token?")
    ? json({ access_token: "other-token", user: otherUser })
    : json({ ...activeProfile, ...otherUser }));
  source.mount(t);
  other.mount(t);
  await source.context().signIn("customer@example.com", "password-123");
  await other.context().signIn("other@example.com", "password-123");
  const fragment = source.chartSessionFragment(source.context().chartSessionId);
  assert.match(fragment, /^#session=[0-9a-f-]{36}$/);

  const chart = authHarness(async (url) => url.includes("/logout")
    ? new Response(null, { status: 204 })
    : json(activeProfile), `https://site.example.test/chart/BANKNIFTY?provider=upstox&days=14${fragment}`);
  chart.mount(t);
  await waitForAuth(() => !chart.context().loading);
  assert.equal(chart.context().session?.user.id, userId);
  assert.equal(chart.context().chartSessionId, source.context().chartSessionId);
  assert.equal(chart.calls.length, 1);
  assert.equal(chart.calls[0].url, "https://api.example.test/api/v1/auth/me");
  assert.equal(chart.calls[0].options.headers.Authorization, "Bearer test-token");
  assert.equal(chart.location.href, "https://site.example.test/chart/BANKNIFTY?provider=upstox&days=14");

  await chart.context().signOut();
  await waitForAuth(() => source.context().session === null);
  assert.equal(other.context().session.user.id, otherId);
});

test("a chart tab rejects a shared credential when the account service denies access", async (t) => {
  const source = authHarness(async (url) => url.includes("/token?") ? json(authReply) : json(activeProfile));
  source.mount(t);
  await source.context().signIn("customer@example.com", "password-123");
  const fragment = source.chartSessionFragment(source.context().chartSessionId);
  const chart = authHarness(() => json({ detail: "Account paused" }, 403), `https://site.example.test/chart/NIFTY50${fragment}`);
  chart.mount(t);
  await waitForAuth(() => !chart.context().loading);
  assert.equal(chart.calls.length, 1);
  assert.equal(chart.context().session, null);
  assert.equal(chart.context().profile, null);
});

test("a chart tab cannot restore a shared session after its source signs out", async (t) => {
  const source = authHarness(async (url) => {
    if (url.includes("/logout")) return new Response(null, { status: 204 });
    return url.includes("/token?") ? json(authReply) : json(activeProfile);
  });
  source.mount(t);
  await source.context().signIn("customer@example.com", "password-123");
  const fragment = source.chartSessionFragment(source.context().chartSessionId);

  let finishProfile;
  const chart = authHarness(() => new Promise((resolve) => { finishProfile = resolve; }), `https://site.example.test/chart/NIFTY50${fragment}`);
  chart.mount(t);
  await waitForAuth(() => Boolean(finishProfile));
  await source.context().signOut();
  await waitForAuth(() => !chart.context().loading);
  finishProfile(json(activeProfile));
  await delay(0);
  assert.equal(chart.context().session, null);
  assert.equal(chart.context().profile, null);
});

test("a chart tab with no open source resolves to signed out without an API call", async (t) => {
  const fragment = `#session=${webcrypto.randomUUID()}`;
  const chart = authHarness(
    () => assert.fail("An invitation without an open source must not make an API request"),
    `https://site.example.test/chart/BANKNIFTY?provider=upstox${fragment}`,
  );
  chart.mount(t);
  assert.equal(chart.context().loading, true);
  await waitForAuth(() => !chart.context().loading);
  assert.equal(chart.context().session, null);
  assert.equal(chart.location.href, "https://site.example.test/chart/BANKNIFTY?provider=upstox");
  assert.equal(chart.calls.length, 0);
});

test("terminal includes the separate Upstox 15-minute historical chart", () => {
  compile("src/components/Upstox15mHistory.tsx");
  const component = fs.readFileSync(path.join(webRoot, "src/components/Upstox15mHistory.tsx"), "utf8");
  const terminal = fs.readFileSync(path.join(webRoot, "src/app/terminal/page.tsx"), "utf8");
  assert.match(component, /market-data\/upstox\/candles\?symbol=/);
  assert.match(component, /Last 7 days/);
  assert.match(component, /Last 30 days/);
  assert.doesNotMatch(component, /slice\(-60\)/);
  assert.match(terminal, /<Upstox15mHistory\s*\/>/);
});

test("customer return destinations accept only supported local routes", () => {
  const moduleObj = { exports: {} };
  vm.runInNewContext(compile("src/lib/customerNavigation.ts"), { module: moduleObj, exports: moduleObj.exports, URLSearchParams });
  const destination = moduleObj.exports.customerDestination;
  assert.equal(destination("?next=%2Faccount"), "/account");
  assert.equal(destination("?next=%2Fterminal"), "/terminal");
  const selectChart = (next) => destination(new URLSearchParams({ next }).toString());
  assert.equal(selectChart("/chart/NIFTY50"), "/chart/NIFTY50");
  assert.equal(selectChart("/chart/BANKNIFTY?provider=upstox&days=14"), "/chart/BANKNIFTY?provider=upstox&days=14");
  assert.equal(selectChart("/chart/BANKNIFTY?provider=upstox&days=31&redirect=https://evil.test"), "/chart/BANKNIFTY?provider=upstox");
  assert.equal(selectChart("/chart/NIFTY50?provider=groww&days=7"), "/chart/NIFTY50?provider=groww");
  assert.equal(selectChart("//evil.test/chart/NIFTY50"), "/terminal");
  assert.equal(selectChart("/chart/NOTANINDEX"), "/terminal");
  for (const search of ["", "?next=https://evil.test", "?next=//evil.test", "?next=javascript:alert(1)", "?next=/admin", "?next=/terminal?url=https://evil.test"]) {
    assert.equal(destination(search), "/terminal");
  }
});

function dashboardHarness() {
  const slots = [];
  let cursor = 0;
  let effect;
  let interval;
  let failureStatus = 0;
  let stale = false;
  let signedOut = false;
  const requests = [];
  const localStorage = new Map();
  const moduleObj = { exports: {} };
  const hooks = {
    useState: (initial) => {
      const slot = cursor++;
      if (!(slot in slots)) slots[slot] = initial;
      return [slots[slot], (value) => { slots[slot] = typeof value === "function" ? value(slots[slot]) : value; }];
    },
    useRef: (initial) => {
      const slot = cursor++;
      if (!(slot in slots)) slots[slot] = { current: initial };
      return slots[slot];
    },
    useCallback: (callback) => callback,
    useEffect: (callback) => { effect = callback; },
  };
  vm.runInNewContext(compile("src/components/LiveMarketDashboard.tsx"), {
    module: moduleObj, exports: moduleObj.exports,
    require: (name) => {
      if (name === "react") return hooks;
      if (name === "react/jsx-runtime") return {
        jsx: (type, props) => typeof type === "function" ? type(props) : ({ type, props }),
        jsxs: (type, props) => typeof type === "function" ? type(props) : ({ type, props }),
      };
      if (name === "next/link") return { default: "a" };
      if (name === "@/components/auth/AuthProvider") return {
        chartSessionFragment: (sessionId) => sessionId ? `#session=${sessionId}` : "",
        useAuth: () => ({
          session: { access_token: "test-token" },
          chartSessionId: userId,
          signOut: async () => { signedOut = true; },
        }),
      };
      throw new Error("Unexpected import: " + name);
    },
    process: { env: { NEXT_PUBLIC_API_BASE_URL: "https://api.example.test" } },
    AbortSignal, AbortController, Intl, Date, console,
    window: {
      localStorage: {
        getItem: (key) => localStorage.get(key) ?? null,
        setItem: (key, value) => localStorage.set(key, value),
      },
      setInterval: (callback) => { interval = callback; return 1; },
      clearInterval: () => {},
    },
    fetch: async (url, options) => {
      requests.push(String(url));
      assert.equal(options.credentials, "omit");
      assert.ok(options.signal instanceof AbortSignal);
      if (failureStatus) return json({ detail: "failed" }, failureStatus);
      if (url.includes("/providers")) return json({ providers: [
        { id: "groww", label: "Groww", configured: true, feed_state: "live", connected: true, message: "Connected" },
        { id: "upstox", label: "Upstox", configured: true, feed_state: "live", connected: true, message: "Connected" },
      ] });
      if (url.includes("/status")) return json({
        feed_state: "live", provider: "groww", streaming_enabled: true, connected: true, session_open: true, instruments: {},
      });
      if (url.includes("/quote")) return json({
        available: true, feed_state: stale ? "stale" : "live", is_stale: stale,
        quote: { ltp: 100, timestamp: "2026-11-15T09:00:00Z" },
      });
      if (url.includes("/forming-candle")) return json({ available: false, forming_candle: null });
      return json({
        feed_state: "live", message: "Feed current", candles: [
          { timestamp: "2026-11-15T08:45:00Z", open: 90, high: 105, low: 89, close: 100, is_forming: false, timeframe: "15m" },
        ], indicator_decision: {
          decision: "BUY", is_current_signal: true, candle_timestamp: "2026-11-15T08:45:00Z",
          reason: "BUY signal confirmed", ut_bot_signal: "BUY", ema_bullish: true,
          rsi_bullish: true, macd_bullish: true, supertrend_bullish: true,
        },
      });
    },
  });
  const render = () => { cursor = 0; return moduleObj.exports.default(); };
  return {
    render,
    chooseProvider: (provider) => {
      const visit = (node) => {
        if (!node || typeof node !== "object") return null;
        if (node.props?.id === "market-data-provider") return node;
        const children = node.props?.children;
        for (const child of Array.isArray(children) ? children : [children]) {
          const match = visit(child);
          if (match) return match;
        }
        return null;
      };
      const select = visit(render());
      assert.ok(select, "provider selector should be rendered");
      select.props.onChange({ target: { value: provider } });
      render();
    },
    start: () => effect(),
    poll: () => interval(),
    fail: (status) => { failureStatus = status; },
    stale: () => { stale = true; },
    snapshots: () => slots[3],
    view: () => render(),
    requests: () => requests,
    signedOut: () => signedOut,
  };
}

async function settleUntil(predicate) {
  for (let attempt = 0; attempt < 50 && !predicate(); attempt++) {
    await new Promise((resolve) => setImmediate(resolve));
  }
  assert.ok(predicate(), "Expected async dashboard state did not settle");
}

test("a failed market refresh clears previously displayed price and candles", async () => {
  const dashboard = dashboardHarness();
  dashboard.render();
  const cleanup = dashboard.start();
  await settleUntil(() => dashboard.snapshots().NIFTY50.current);
  assert.equal(dashboard.snapshots().NIFTY50.current, true);
  assert.equal(dashboard.snapshots().NIFTY50.quote.ltp, 100);
  assert.equal(dashboard.snapshots().NIFTY50.candles.length, 1);
  dashboard.fail(503);
  dashboard.poll();
  await settleUntil(() => Boolean(dashboard.snapshots().NIFTY50.error));
  assert.equal(dashboard.snapshots().NIFTY50.current, false);
  assert.equal(dashboard.snapshots().NIFTY50.quote, null);
  assert.equal(dashboard.snapshots().NIFTY50.candles.length, 0);
  cleanup();
});

test("an expired terminal authorization clears the session instead of polling indefinitely", async () => {
  const dashboard = dashboardHarness();
  dashboard.render();
  dashboard.fail(401);
  const cleanup = dashboard.start();
  await settleUntil(() => dashboard.signedOut());
  assert.equal(dashboard.snapshots().NIFTY50.quote, null);
  cleanup();
});

test("a server-reported stale quote is retained only as non-current historical data", async () => {
  const dashboard = dashboardHarness();
  dashboard.render();
  dashboard.stale();
  const cleanup = dashboard.start();
  await settleUntil(() => dashboard.snapshots().NIFTY50.quote !== null);
  assert.equal(dashboard.snapshots().NIFTY50.current, false);
  assert.equal(dashboard.snapshots().NIFTY50.feedState, "stale");
  assert.equal(dashboard.snapshots().NIFTY50.candles.length, 1);
  assert.doesNotMatch(JSON.stringify(dashboard.view()), /Current confirmed signal/);
  cleanup();
});

test("customers can select Upstox and the dashboard requests data from that provider", async () => {
  const dashboard = dashboardHarness();
  dashboard.chooseProvider("upstox");
  const cleanup = dashboard.start();
  await settleUntil(() => dashboard.requests().some((url) => url.includes("/api/v1/live/quote?") && url.includes("provider=upstox")));
  assert.ok(dashboard.requests().some((url) => url.includes("/api/v1/live/status?provider=upstox")));
  assert.ok(dashboard.requests().some((url) => url.includes("/api/v1/live/candles?") && url.includes("provider=upstox")));
  assert.ok(dashboard.requests().some((url) => url.includes("timeframe=15m")));
  cleanup();
});

test("each index title opens a separate chart tab and shows the latest decision", async () => {
  const dashboard = dashboardHarness();
  dashboard.render();
  const cleanup = dashboard.start();
  await settleUntil(() => dashboard.snapshots().NIFTY50.decision?.decision === "BUY");
  const visit = (node, found = []) => {
    if (!node || typeof node !== "object") return found;
    if (node.type === "a") found.push(node);
    const children = node.props?.children;
    for (const child of Array.isArray(children) ? children : [children]) visit(child, found);
    return found;
  };
  const links = visit(dashboard.view());
  for (const symbol of ["NIFTY50", "BANKNIFTY"]) {
    assert.ok(links.some((link) => link.props?.href === `/chart/${symbol}?provider=groww#session=${userId}` && link.props?.target === "_blank"));
  }
  assert.equal(dashboard.snapshots().NIFTY50.decision.decision, "BUY");
  assert.ok(dashboard.requests().some((url) => url.includes("timeframe=15m")));
  cleanup();
});
