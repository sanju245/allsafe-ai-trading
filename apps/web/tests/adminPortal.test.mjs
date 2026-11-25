import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import ts from "typescript";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const fullPath = path.join(webRoot, "src/components/admin/AdminUsersPanel.tsx");
const compiled = ts.transpileModule(fs.readFileSync(fullPath, "utf8"), {
  fileName: fullPath,
  compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

function harness() {
  const slots = [];
  const effects = [];
  let cursor = 0;
  let tree;
  let fetchStatus = 200;
  let customerEmail = "private-customer@example.com";
  let deferredResponse = null;
  const calls = { signOut: 0, refreshProfile: 0, fetch: 0 };
  const auth = {
    session: { access_token: "verified-admin-token" },
    profile: { role: "admin", status: "active" },
    loading: false,
    async signOut() {
      calls.signOut++;
      auth.session = null;
      auth.profile = null;
    },
    async refreshProfile() {
      calls.refreshProfile++;
      auth.profile = { role: "user", status: "active" };
    },
  };
  const hooks = {
    useState(initial) {
      const i = cursor++;
      if (!(i in slots)) slots[i] = typeof initial === "function" ? initial() : initial;
      return [slots[i], (value) => { slots[i] = typeof value === "function" ? value(slots[i]) : value; }];
    },
    useRef(initial) {
      const i = cursor++;
      if (!(i in slots)) slots[i] = { current: initial };
      return slots[i];
    },
    useMemo(callback) { cursor++; return callback(); },
    useCallback(callback) { cursor++; return callback; },
    useLayoutEffect(callback, deps) {
      const i = cursor++;
      const previous = slots[i];
      if (!previous || deps.some((value, n) => value !== previous.deps[n])) {
        previous?.cleanup?.();
        slots[i] = { deps, cleanup: callback() };
      }
    },
    useEffect(callback, deps) {
      const i = cursor++;
      if (!(i in slots) || deps.some((value, n) => value !== slots[i][n])) {
        slots[i] = deps;
        effects.push(callback);
      }
    },
  };
  const exports = {};
  const moduleObj = { exports };
  const jsx = (type, props) => ({ type, props });
  const sandbox = {
    exports, module: moduleObj, process, console, AbortSignal, Error,
    window: { setTimeout, clearTimeout },
    document: { addEventListener() {}, removeEventListener() {} },
    async fetch() {
      calls.fetch++;
      if (deferredResponse) {
        const response = deferredResponse;
        deferredResponse = null;
        return response;
      }
      const status = fetchStatus;
      const email = customerEmail;
      return {
        ok: status === 200,
        status,
        async json() {
          return status === 200 ? {
            users: [{ id: "customer-id", email, role: "user", status: "active", created_at: "2026-01-01T00:00:00Z" }],
          } : { detail: { message: "Administrator access was denied." } };
        },
      };
    },
    require(name) {
      if (name === "react") return hooks;
      if (name === "react/jsx-runtime") return { jsx, jsxs: jsx, Fragment: "fragment" };
      if (name === "next/link") return { default: "a" };
      if (name === "@/components/auth/AuthProvider") return { useAuth: () => auth };
      if (name === "@/components/admin/AccountRequestsPanel") return { default: "AccountRequestsPanel" };
      if (name === "@/components/admin/CustomerMessageDialog") return { default: "CustomerMessageDialog" };
      if (name === "@/components/admin/CustomerSignInHistory") return { default: "CustomerSignInHistory" };
      throw new Error("Unexpected import: " + name);
    },
  };
  vm.runInNewContext(compiled, sandbox, { filename: fullPath });
  return {
    calls, auth,
    setStatus(status) { fetchStatus = status; },
    setCustomerEmail(email) { customerEmail = email; },
    deferNextResponse(status) {
      let release;
      deferredResponse = new Promise((resolve) => { release = resolve; });
      return () => release({
        ok: status === 200,
        status,
        async json() {
          return status === 200 ? {
            users: [{ id: "old-customer", email: "stale-customer@example.com", role: "user", status: "active", created_at: "2026-01-01T00:00:00Z" }],
          } : { detail: { message: "Old administrator request denied." } };
        },
      });
    },
    render() { cursor = 0; tree = moduleObj.exports.default(); return tree; },
    async flushEffects() { for (const effect of effects.splice(0)) effect(); await new Promise((resolve) => setTimeout(resolve, 5)); },
    get tree() { return tree; },
  };
}

function find(node, predicate) {
  if (!node || typeof node !== "object") return null;
  if (Array.isArray(node)) {
    for (const item of node) { const match = find(item, predicate); if (match) return match; }
    return null;
  }
  if (predicate(node)) return node;
  for (const child of Object.values(node.props ?? {})) {
    if (Array.isArray(child)) {
      for (const item of child) { const match = find(item, predicate); if (match) return match; }
    } else {
      const match = find(child, predicate);
      if (match) return match;
    }
  }
  return null;
}

for (const status of [401, 403]) {
  test("Admin directory clears previously loaded customers after HTTP " + status, async () => {
    const app = harness();
    app.render();
    await app.flushEffects();
    app.render();
    assert.match(JSON.stringify(app.tree), /private-customer@example.com/);

    app.setStatus(status);
    const refresh = find(app.tree, (node) => node.type === "button" && node.props.children === "Refresh list");
    assert.ok(refresh);
    refresh.props.onClick();
    await new Promise((resolve) => setTimeout(resolve, 5));
    app.render();

    assert.doesNotMatch(JSON.stringify(app.tree), /private-customer@example.com|192\.0\.2\.10/);
    assert.equal(app.calls.signOut, status === 401 ? 1 : 0);
    assert.equal(app.calls.refreshProfile, status === 403 ? 1 : 0);
    if (status === 403) {
      assert.ok(app.auth.session, "A customer session must survive an admin-only denial.");
      assert.equal(app.auth.profile.role, "user");
    }
  });
}

test("A denied customer mutation clears the directory and rechecks the role", async () => {
  const app = harness();
  app.render();
  await app.flushEffects();
  app.render();
  const actions = find(app.tree, (node) => typeof node.props?.onStatusChange === "function");
  assert.ok(actions);
  await actions.props.onStatusChange(actions.props.user);
  app.render();
  const dialog = find(app.tree, (node) => node.type === "CustomerMessageDialog");
  assert.equal(dialog.props.action, "pause");
  app.setStatus(403);
  await assert.rejects(dialog.props.save("Example pause reason", "test-request"), /access was denied/);
  app.render();

  assert.doesNotMatch(JSON.stringify(app.tree), /private-customer@example.com|192\.0\.2\.10/);
  assert.equal(app.calls.refreshProfile, 1);
  assert.equal(app.calls.signOut, 0);
  assert.ok(app.auth.session);
});

test("A denied sign-in history request closes the dialog and clears the customer directory", async () => {
  const app = harness();
  app.render();
  await app.flushEffects();
  app.render();
  const actions = find(app.tree, (node) => typeof node.props?.onViewSignIns === "function");
  actions.props.onViewSignIns(actions.props.user);
  app.render();
  const history = find(app.tree, (node) => node.type === "CustomerSignInHistory");
  assert.ok(history);
  assert.equal(history.props.email, "private-customer@example.com");
  app.setStatus(403);
  await assert.rejects(history.props.load(new AbortController().signal), /access was denied/);
  app.render();

  assert.equal(find(app.tree, (node) => node.type === "CustomerSignInHistory"), null);
  assert.doesNotMatch(JSON.stringify(app.tree), /private-customer@example.com/);
  assert.equal(app.calls.refreshProfile, 1);
});

for (const status of [200, 401, 403]) {
  test("An old session's delayed HTTP " + status + " response cannot change a newer sign-in", async () => {
    const app = harness();
    app.render();
    await app.flushEffects();
    app.render();
    const releaseOldResponse = app.deferNextResponse(status);
    const refresh = find(app.tree, (node) => node.type === "button" && node.props.children === "Refresh list");
    refresh.props.onClick();

    app.auth.session = null;
    app.auth.profile = null;
    app.render();
    app.auth.session = { access_token: "new-admin-token" };
    app.auth.profile = { role: "admin", status: "active" };
    app.setCustomerEmail("current-customer@example.com");
    app.render();
    await app.flushEffects();
    app.render();
    assert.match(JSON.stringify(app.tree), /current-customer@example.com/);
    assert.doesNotMatch(JSON.stringify(app.tree), /private-customer@example.com/);

    releaseOldResponse();
    await new Promise((resolve) => setTimeout(resolve, 5));
    app.render();
    assert.equal(app.auth.session.access_token, "new-admin-token");
    assert.equal(app.auth.profile.role, "admin");
    assert.equal(app.calls.signOut, 0);
    assert.equal(app.calls.refreshProfile, 0);
    assert.match(JSON.stringify(app.tree), /current-customer@example.com/);
    assert.doesNotMatch(JSON.stringify(app.tree), /stale-customer@example.com|Old administrator request denied/);
  });
}
