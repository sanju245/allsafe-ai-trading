import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const userId = "00000000-0000-4000-8000-000000000001";
const authReply = { access_token: "test-token", user: { id: userId, email: "customer@example.com" } };
const activeProfile = {
  id: userId, email: "customer@example.com", role: "user", status: "active",
  allowed_ip: "192.0.2.1", client_ip: "192.0.2.1",
};
const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { "Content-Type": "application/json" },
});

function compile(relativePath) {
  const fullPath = path.join(webRoot, relativePath);
  const output = ts.transpileModule(fs.readFileSync(fullPath, "utf8"), {
    fileName: fullPath, reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  });
  assert.equal(output.diagnostics?.length ?? 0, 0);
  return output.outputText;
}

function authHarness(fetchImpl) {
  const slots = [];
  let cursor = 0;
  const calls = [];
  const timeouts = [];
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
    console,
    fetch: async (url, options) => {
      calls.push({ url, options });
      return fetchImpl(url, options);
    },
  });
  return {
    calls,
    timeouts,
    context: () => {
      cursor = 0;
      return moduleObj.exports.AuthProvider({ children: null }).props.value;
    },
  };
}

test("customer sign-in is not restricted by IP and records a successful login event", async () => {
  const harness = authHarness(async (url) => {
    if (url.includes("/token?")) return json(authReply);
    if (url.endsWith("/login-events")) return new Response(null, { status: 204 });
    return json(activeProfile);
  });
  await harness.context().signIn(" customer@example.com ", "password-123");
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(harness.context().session.user.id, userId);
  assert.equal(harness.context().profile.id, userId);
  assert.equal(harness.context().profile.allowed_ip, undefined);
  assert.equal(harness.context().loginAuditRecorded, true);
  assert.equal(harness.context().loading, false);
  assert.equal(JSON.parse(harness.calls[0].options.body).email, "customer@example.com");
  assert.ok(harness.calls.some(({ url, options }) => url.endsWith("/api/v1/auth/login-events") && options.method === "POST"));
  assert.deepEqual(harness.timeouts, [12000, 65000, 12000]);
  for (const { options } of harness.calls) {
    assert.equal(options.credentials, "omit");
    assert.ok(options.signal instanceof AbortSignal);
  }
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

test("login-history storage trouble never becomes a customer IP restriction", async () => {
  const harness = authHarness(async (url) => {
    if (url.includes("/token?")) return json(authReply);
    if (url.includes("/logout")) return new Response(null, { status: 204 });
    if (url.endsWith("/login-events")) return json({ detail: "unavailable" }, 503);
    return json(activeProfile);
  });
  await harness.context().signIn("customer@example.com", "password-123");
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(harness.context().session.user.id, userId);
  assert.equal(harness.context().loginAuditRecorded, false);
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

test("active admin sign-in is audited without returning IP fields in the profile", async () => {
  const harness = authHarness(async (url) => {
    if (url.includes("/token?")) return json(authReply);
    if (url.endsWith("/login-events")) return new Response(null, { status: 204 });
    return json({ ...activeProfile, role: "admin" });
  });
  await harness.context().signIn("admin@example.com", "password-123");
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(harness.context().profile.role, "admin");
  assert.equal(harness.context().profile.client_ip, undefined);
  assert.equal(harness.context().loginAuditRecorded, true);
});

test("customer return destinations accept only supported local routes", () => {
  const moduleObj = { exports: {} };
  vm.runInNewContext(compile("src/lib/customerNavigation.ts"), { module: moduleObj, exports: moduleObj.exports, URLSearchParams });
  const destination = moduleObj.exports.customerDestination;
  assert.equal(destination("?next=%2Faccount"), "/account");
  assert.equal(destination("?next=%2Fterminal"), "/terminal");
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
        jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }),
      };
      if (name === "@/components/auth/AuthProvider") return {
        useAuth: () => ({
          session: { access_token: "test-token" },
          signOut: async () => { signedOut = true; },
        }),
      };
      throw new Error("Unexpected import: " + name);
    },
    process: { env: { NEXT_PUBLIC_API_BASE_URL: "https://api.example.test" } },
    AbortSignal, AbortController, Intl, Date, console,
    window: { setInterval: (callback) => { interval = callback; return 1; }, clearInterval: () => {} },
    fetch: async (url, options) => {
      assert.equal(options.credentials, "omit");
      assert.ok(options.signal instanceof AbortSignal);
      if (failureStatus) return json({ detail: "failed" }, failureStatus);
      if (url.includes("/status")) return json({
        feed_state: "live", streaming_enabled: true, connected: true, session_open: true, instruments: {},
      });
      if (url.includes("/quote")) return json({
        available: true, feed_state: stale ? "stale" : "live", is_stale: stale,
        quote: { ltp: 100, timestamp: "2026-11-15T09:00:00Z" },
      });
      if (url.includes("/forming-candle")) return json({ available: false, forming_candle: null });
      return json({
        feed_state: "live", message: "Feed current", candles: [
          { timestamp: "2026-11-15T08:55:00Z", open: 90, high: 105, low: 89, close: 100, is_forming: false },
        ],
      });
    },
  });
  return {
    render: () => { cursor = 0; return moduleObj.exports.default(); },
    start: () => effect(),
    poll: () => interval(),
    fail: (status) => { failureStatus = status; },
    stale: () => { stale = true; },
    snapshots: () => slots[1],
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
  cleanup();
});
