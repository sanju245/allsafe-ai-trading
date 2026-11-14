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

test("Client/Server API Boundary: clientApi.ts and api.ts export API_BASE_URL, fetchApi, AuthApiError, and getApiHealth without leaking server-only env vars to browser bundle", () => {
  const clientApiPath = path.join(webRoot, "src/lib/clientApi.ts");
  const serverApiPath = path.join(webRoot, "src/lib/api.ts");

  assert.equal(fs.existsSync(clientApiPath), true, "src/lib/clientApi.ts must exist");
  assert.equal(fs.existsSync(serverApiPath), true, "src/lib/api.ts must exist");

  const clientApiSrc = fs.readFileSync(clientApiPath, "utf8");
  const serverApiSrc = fs.readFileSync(serverApiPath, "utf8");

  // Verify clientApi.ts only uses NEXT_PUBLIC_API_BASE_URL and never reads server-only process.env.API_BASE_URL
  assert.equal(
    /process\.env\.API_BASE_URL/.test(clientApiSrc),
    false,
    "clientApi.ts must not reference server-only process.env.API_BASE_URL",
  );
  assert.match(clientApiSrc, /process\.env\.NEXT_PUBLIC_API_BASE_URL/);

  // Compile and execute clientApi.ts in an isolated VM sandbox
  const transformedClient = babel.transformSync(clientApiSrc, {
    filename: clientApiPath,
    presets: [
      [requireWithFallback("@babel/preset-env"), { targets: { node: "current" }, modules: "commonjs" }],
      requireWithFallback("@babel/preset-typescript"),
    ],
  });

  const exportsObj = {};
  const moduleObj = { exports: exportsObj };
  const sandbox = {
    exports: exportsObj,
    module: moduleObj,
    process: { env: { NODE_ENV: "production", NEXT_PUBLIC_API_BASE_URL: "https://allsafe-ai-api.onrender.com/" } },
    fetch: async (url, init) => ({
      ok: true,
      status: 200,
      json: async () => ({ url, headers: init.headers, credentials: init.credentials }),
    }),
    Error,
    Object,
    String,
  };
  vm.runInNewContext(transformedClient.code, sandbox);

  assert.equal(moduleObj.exports.PUBLIC_API_BASE_URL, "https://allsafe-ai-api.onrender.com");
  assert.equal(moduleObj.exports.API_BASE_URL, "https://allsafe-ai-api.onrender.com");
  assert.equal(typeof moduleObj.exports.fetchApi, "function");
  assert.equal(typeof moduleObj.exports.AuthApiError, "function");

  // Verify server api.ts re-exports API_BASE_URL and fetchApi so login/page.tsx and admin/page.tsx imports succeed
  assert.match(serverApiSrc, /API_BASE_URL/);
  assert.match(serverApiSrc, /fetchApi/);
  assert.match(serverApiSrc, /export async function getApiHealth/);
});

test("Admin Portal (/admin/login & /admin) and Customer Portal (/login & /terminal) separation and route guards", () => {
  const adminLoginSrc = fs.readFileSync(path.join(webRoot, "src/app/admin/login/page.tsx"), "utf8");
  const customerLoginSrc = fs.readFileSync(path.join(webRoot, "src/app/login/page.tsx"), "utf8");
  const gateSrc = fs.readFileSync(path.join(webRoot, "src/components/auth/DashboardAccessGate.tsx"), "utf8");
  const terminalSrc = fs.readFileSync(path.join(webRoot, "src/app/terminal/page.tsx"), "utf8");

  // 1. Admin Portal Login (/admin/login) posts to /api/v1/auth/admin/login with portal: "admin" and blocks customer accounts
  assert.match(adminLoginSrc, /\/api\/v1\/auth\/admin\/login/);
  assert.match(adminLoginSrc, /portal:\s*"admin"/);
  assert.match(adminLoginSrc, /Customer accounts cannot sign in to the Admin Portal/);

  // 2. Customer Portal Login (/login) links to /admin/login for administrators and highlights customer IP protection
  assert.match(customerLoginSrc, /Customer Portal Sign-In/);
  assert.match(customerLoginSrc, /Customer IP Policy/);
  assert.match(customerLoginSrc, /\/admin\/login/);

  // 3. DashboardAccessGate routes unauthenticated admin requests to /admin/login and blocks non-admin users from /admin
  assert.match(gateSrc, /const loginRoute = requireAdmin \? "\/admin\/login" : "\/login"/);
  assert.match(gateSrc, /if \(requireAdmin && !hasAdminAccess\(user\.role, user\.is_super_admin\)\)/);
  assert.match(gateSrc, /router\.replace\("\/terminal"\)/);

  // 4. All routes compile cleanly via Babel TypeScript + React preset and disclose zero indicator names
  const forbiddenIndicatorRegex =
    /\b(UT\s*Bot|ut_bot|EMA|RSI|MACD|Supertrend|supertrend|ATR|ROC|Wilder|Heikin[\s-]*Ashi)\b/i;
  assert.equal(
    forbiddenIndicatorRegex.test(terminalSrc),
    false,
    "terminal/page.tsx must not disclose proprietary indicator names",
  );

  for (const rel of [
    "src/lib/clientApi.ts",
    "src/lib/api.ts",
    "src/app/login/page.tsx",
    "src/app/admin/login/page.tsx",
    "src/app/admin/page.tsx",
    "src/app/terminal/page.tsx",
    "src/app/account/page.tsx",
    "src/app/page.tsx",
    "src/app/what-we-done/page.tsx",
  ]) {
    const full = path.join(webRoot, rel);
    const src = fs.readFileSync(full, "utf8");
    const presets = [requireWithFallback("@babel/preset-typescript")];
    if (rel.endsWith(".tsx")) {
      presets.push([
        requireWithFallback("@babel/preset-react"),
        { runtime: "automatic" },
      ]);
    }
    const compiled = babel.transformSync(src, {
      filename: full,
      presets,
    });
    assert.ok(compiled && compiled.code && compiled.code.length > 0, `Failed to compile ${rel}`);
  }
});

let cachedCompilation = null;
function compileAdminUsersPanel() {
  if (cachedCompilation) return cachedCompilation;
  const adminUsersPath = path.join(webRoot, "src/components/admin/AdminUsersPanel.tsx");
  const adminUsersSrc = fs.readFileSync(adminUsersPath, "utf8");
  const compiled = babel.transformSync(adminUsersSrc, {
    filename: adminUsersPath,
    presets: [
      [requireWithFallback("@babel/preset-env"), { targets: { node: "current" }, modules: "commonjs" }],
      requireWithFallback("@babel/preset-typescript"),
      [requireWithFallback("@babel/preset-react"), { runtime: "classic" }],
    ],
  });
  cachedCompilation = { adminUsersPath, adminUsersSrc, code: compiled.code };
  return cachedCompilation;
}

function createPanelHarness({
  onDirectoryChanged,
  fetchResponder,
  authOverride,
} = {}) {
  const { code } = compileAdminUsersPanel();
  const stateSlots = [];
  const refSlots = [];
  let hookCursor = 0;

  const ReactMock = {
    createElement: (type, props, ...children) => ({
      type,
      props: {
        ...(props || {}),
        children: children.length <= 1 ? children[0] : children,
      },
    }),
    useState: (initialValue) => {
      const idx = hookCursor++;
      if (!(idx in stateSlots)) {
        stateSlots[idx] = typeof initialValue === "function" ? initialValue() : initialValue;
      }
      const setState = (updater) => {
        stateSlots[idx] = typeof updater === "function" ? updater(stateSlots[idx]) : updater;
      };
      return [stateSlots[idx], setState];
    },
    useRef: (initialValue) => {
      const idx = hookCursor++;
      if (!(idx in refSlots)) {
        refSlots[idx] = { current: initialValue };
      }
      return refSlots[idx];
    },
    useCallback: (fn) => fn,
    useMemo: (fn) => fn(),
    useEffect: () => {},
  };

  const fetchCalls = [];
  const fetchMock = async (url, init = {}) => {
    const method = init.method ?? "GET";
    const parsedBody = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
    fetchCalls.push({ url, method, headers: init.headers, body: parsedBody });
    if (fetchResponder) {
      return fetchResponder(url, method, parsedBody, init);
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ users: [] }),
    };
  };

  const authValue = authOverride ?? {
    session: { access_token: "admin-access-token" },
    user: { id: "admin-1", email: "admin@allsafe.ai", role: "admin", status: "active" },
    loading: false,
    signOut: async () => {},
  };

  const customRequire = (id) => {
    if (id === "react") return ReactMock;
    if (id === "next/link") {
      return {
        __esModule: true,
        default: function LinkMock(props) {
          return ReactMock.createElement("a", props, props.children);
        },
      };
    }
    if (id === "@/components/auth/AuthProvider") {
      return {
        useAuth: () => authValue,
      };
    }
    throw new Error(`Unexpected import in AdminUsersPanel: ${id}`);
  };

  const exportsObj = {};
  const moduleObj = { exports: exportsObj };
  const sandbox = {
    exports: exportsObj,
    module: moduleObj,
    require: customRequire,
    React: ReactMock,
    process: { env: { NODE_ENV: "production", NEXT_PUBLIC_API_BASE_URL: "https://allsafe-ai-api.onrender.com" } },
    fetch: fetchMock,
    window: {
      setTimeout: (fn) => {
        fn();
        return 1;
      },
      clearTimeout: () => {},
    },
    document: {
      addEventListener: () => {},
      removeEventListener: () => {},
      activeElement: null,
    },
    HTMLElement: class HTMLElementMock {},
    Date,
    Error,
    JSON,
    Number,
    Object,
    Promise,
    String,
    Boolean,
    Array,
    encodeURIComponent,
  };

  vm.runInNewContext(code, sandbox);

  function render() {
    hookCursor = 0;
    return moduleObj.exports.AdminUsersPanel({ onDirectoryChanged });
  }

  function findNodes(node, predicate, acc = []) {
    if (!node || typeof node !== "object") return acc;
    if (Array.isArray(node)) {
      for (const item of node) findNodes(item, predicate, acc);
      return acc;
    }
    if (predicate(node)) acc.push(node);
    const children = node.props?.children;
    if (Array.isArray(children)) {
      for (const child of children) findNodes(child, predicate, acc);
    } else if (children) {
      findNodes(children, predicate, acc);
    }
    return acc;
  }

  function textOf(node) {
    if (node === null || node === undefined || typeof node === "boolean") return "";
    if (typeof node === "string" || typeof node === "number") return String(node);
    if (Array.isArray(node)) return node.map(textOf).join("");
    if (typeof node === "object" && node.props) return textOf(node.props.children);
    return "";
  }

  const flushAsync = async () => {
    for (let i = 0; i < 6; i += 1) {
      await new Promise((resolve) => setImmediate(resolve));
    }
  };

  return {
    exports: moduleObj.exports,
    stateSlots,
    fetchCalls,
    render,
    findNodes,
    textOf,
    flushAsync,
  };
}

test("AdminUsersPanel structure, exports, props, and useAuth() contract match local baseline", () => {
  const { adminUsersSrc } = compileAdminUsersPanel();
  const harness = createPanelHarness();

  // Named and default exports exist and point to the same component function
  assert.equal(typeof harness.exports.AdminUsersPanel, "function");
  assert.equal(typeof harness.exports.default, "function");
  assert.equal(harness.exports.AdminUsersPanel, harness.exports.default);

  // Preserves useAuth() destructuring `user: profile` and the four local mutation handlers
  assert.match(adminUsersSrc, /const\s+\{\s*session,\s*user:\s*profile,\s*loading:\s*authLoading,\s*signOut\s*\}\s*=\s*useAuth\(\)/);
  assert.match(adminUsersSrc, /async\s+function\s+createUser\s*\(/);
  assert.match(adminUsersSrc, /async\s+function\s+changeStatus\s*\(/);
  assert.match(adminUsersSrc, /async\s+function\s+changeAllowedIp\s*\(/);
  assert.match(adminUsersSrc, /async\s+function\s+deleteUser\s*\(/);
});

test("AdminUsersPanel invokes onDirectoryChanged after each of the four successful mutations (createUser, changeStatus, changeAllowedIp, deleteUser)", async () => {
  let directoryCallbackCount = 0;
  let directoryUsers = [
    {
      id: "cust-1",
      email: "alice@example.com",
      role: "customer",
      status: "active",
      allowed_ip: "203.0.113.10",
      created_at: "2026-11-01T00:00:00Z",
    },
  ];

  const harness = createPanelHarness({
    onDirectoryChanged: () => {
      directoryCallbackCount += 1;
    },
    fetchResponder: async (url, method, body) => {
      if (method === "GET" && url.endsWith("/api/v1/admin/users")) {
        return { ok: true, status: 200, json: async () => ({ users: directoryUsers.map((u) => ({ ...u })) }) };
      }
      if (method === "POST" && url.endsWith("/api/v1/admin/users")) {
        directoryUsers = [
          ...directoryUsers,
          {
            id: "cust-2",
            email: body.email,
            role: "customer",
            status: "active",
            allowed_ip: body.allowed_ip,
            created_at: "2026-11-08T00:00:00Z",
          },
        ];
        return { ok: true, status: 201, json: async () => ({ id: "cust-2" }) };
      }
      if (method === "PATCH" && url.includes("/api/v1/admin/users/")) {
        const targetId = decodeURIComponent(url.split("/api/v1/admin/users/")[1]);
        directoryUsers = directoryUsers.map((u) => (u.id === targetId ? { ...u, ...body } : u));
        return { ok: true, status: 200, json: async () => ({ ok: true }) };
      }
      if (method === "DELETE" && url.includes("/api/v1/admin/users/")) {
        const targetId = decodeURIComponent(url.split("/api/v1/admin/users/")[1]);
        directoryUsers = directoryUsers.filter((u) => u.id !== targetId);
        return { ok: true, status: 204, json: async () => ({}) };
      }
      throw new Error(`Unexpected request: ${method} ${url}`);
    },
  });

  // Initial render & manual "Refresh list" button load users without firing onDirectoryChanged
  let tree = harness.render();
  const refreshBtn = harness.findNodes(
    tree,
    (n) => n.type === "button" && harness.textOf(n).includes("Refresh list"),
  )[0];
  assert.ok(refreshBtn, "Refresh list button must exist");
  refreshBtn.props.onClick();
  await harness.flushAsync();
  assert.equal(directoryCallbackCount, 0, "Refresh list must not invoke onDirectoryChanged");

  // 1. createUser mutation
  tree = harness.render();
  const openCreateBtn = harness.findNodes(
    tree,
    (n) => n.type === "button" && harness.textOf(n).includes("Create customer"),
  )[0];
  openCreateBtn.props.onClick();
  tree = harness.render();

  const emailInput = harness.findNodes(tree, (n) => n.type === "input" && n.props?.placeholder === "customer@example.com")[0];
  const passwordInput = harness.findNodes(tree, (n) => n.type === "input" && n.props?.placeholder === "At least 8 characters")[0];
  const ipInput = harness.findNodes(tree, (n) => n.type === "input" && n.props?.placeholder === "Customer's public IPv4 or IPv6")[0];
  emailInput.props.onChange({ target: { value: "  bob@example.com  " } });
  passwordInput.props.onChange({ target: { value: "SecretPass123!" } });
  ipInput.props.onChange({ target: { value: " 198.51.100.42 " } });

  tree = harness.render();
  const createForm = harness.findNodes(tree, (n) => n.type === "form")[0];
  await createForm.props.onSubmit({ preventDefault() {} });
  await harness.flushAsync();

  assert.equal(directoryCallbackCount, 1, "onDirectoryChanged must be called once after createUser succeeds");
  assert.equal(harness.stateSlots[4], "Created the account for bob@example.com.");
  assert.equal(harness.stateSlots[3], null);

  // 2. changeStatus mutation
  tree = harness.render();
  const userActionsNodes = harness.findNodes(
    tree,
    (n) => typeof n.type === "function" && n.type.name === "UserActions",
  );
  assert.ok(userActionsNodes.length > 0, "UserActions row components must be rendered");
  const aliceActionsProps = userActionsNodes.find((n) => n.props.user.id === "cust-1").props;
  await aliceActionsProps.onStatusChange(aliceActionsProps.user);
  await harness.flushAsync();

  assert.equal(directoryCallbackCount, 2, "onDirectoryChanged must be called once after changeStatus succeeds");
  assert.equal(harness.stateSlots[4], "alice@example.com login paused.");
  assert.equal(harness.stateSlots[3], null);

  // 3. changeAllowedIp mutation
  tree = harness.render();
  const updatedAliceProps = harness
    .findNodes(tree, (n) => typeof n.type === "function" && n.type.name === "UserActions")
    .find((n) => n.props.user.id === "cust-1").props;
  const ipSaved = await updatedAliceProps.onAllowedIpChange(updatedAliceProps.user, "203.0.113.99");
  await harness.flushAsync();

  assert.equal(ipSaved, true, "changeAllowedIp must resolve to true on success");
  assert.equal(directoryCallbackCount, 3, "onDirectoryChanged must be called once after changeAllowedIp succeeds");
  assert.equal(harness.stateSlots[4], "Allowed IP updated for alice@example.com.");
  assert.equal(harness.stateSlots[3], null);

  // 4. deleteUser mutation (with confirmation guard verification)
  updatedAliceProps.onDelete(updatedAliceProps.user);
  tree = harness.render();

  const confirmInput = harness.findNodes(
    tree,
    (n) => n.type === "input" && n.props?.type === "email" && n.props?.autoFocus === true,
  )[0];
  assert.ok(confirmInput, "Delete confirmation email input must render");
  confirmInput.props.onChange({ target: { value: "alice@example.com" } });

  tree = harness.render();
  const confirmDeleteBtn = harness.findNodes(
    tree,
    (n) => n.type === "button" && harness.textOf(n).includes("Delete customer"),
  )[0];
  const fetchCountBeforeDelete = harness.fetchCalls.length;
  confirmDeleteBtn.props.onClick();
  await harness.flushAsync();

  assert.equal(directoryCallbackCount, 4, "onDirectoryChanged must be called once after deleteUser succeeds");
  assert.equal(harness.fetchCalls.length, fetchCountBeforeDelete + 1, "deleteUser updates local state without an extra GET");
  assert.equal(harness.fetchCalls[harness.fetchCalls.length - 1].method, "DELETE");
  assert.equal(harness.stateSlots[4], "Deleted the account for alice@example.com.");
  assert.equal(harness.stateSlots[3], null);
  assert.equal(harness.stateSlots[0].some((u) => u.id === "cust-1"), false, "Deleted customer must be removed from local state");
});

test("AdminUsersPanel does NOT invoke onDirectoryChanged when any of the four API mutations fail", async () => {
  let directoryCallbackCount = 0;
  const initialUsers = [
    {
      id: "cust-1",
      email: "alice@example.com",
      role: "customer",
      status: "active",
      allowed_ip: "203.0.113.10",
      created_at: "2026-11-01T00:00:00Z",
    },
  ];

  const harness = createPanelHarness({
    onDirectoryChanged: () => {
      directoryCallbackCount += 1;
    },
    fetchResponder: async (url, method) => {
      if (method === "GET") {
        return { ok: true, status: 200, json: async () => ({ users: initialUsers }) };
      }
      return {
        ok: false,
        status: 500,
        json: async () => ({ detail: `Simulated ${method} failure` }),
      };
    },
  });

  // Load initial directory
  let tree = harness.render();
  const refreshBtn = harness.findNodes(tree, (n) => n.type === "button" && harness.textOf(n).includes("Refresh list"))[0];
  refreshBtn.props.onClick();
  await harness.flushAsync();

  // 1. Failed createUser
  tree = harness.render();
  const openCreateBtn = harness.findNodes(tree, (n) => n.type === "button" && harness.textOf(n).includes("Create customer"))[0];
  openCreateBtn.props.onClick();
  tree = harness.render();
  harness.findNodes(tree, (n) => n.type === "input" && n.props?.placeholder === "customer@example.com")[0].props.onChange({
    target: { value: "fail@example.com" },
  });
  harness.findNodes(tree, (n) => n.type === "input" && n.props?.placeholder === "At least 8 characters")[0].props.onChange({
    target: { value: "SecretPass123!" },
  });
  harness.findNodes(tree, (n) => n.type === "input" && n.props?.placeholder === "Customer's public IPv4 or IPv6")[0].props.onChange({
    target: { value: "203.0.113.55" },
  });
  tree = harness.render();
  await harness.findNodes(tree, (n) => n.type === "form")[0].props.onSubmit({ preventDefault() {} });
  await harness.flushAsync();
  assert.equal(directoryCallbackCount, 0, "Failed createUser must not invoke onDirectoryChanged");
  assert.equal(harness.stateSlots[3], "Simulated POST failure");

  // 2. Failed changeStatus
  tree = harness.render();
  const actionsProps = harness.findNodes(tree, (n) => typeof n.type === "function" && n.type.name === "UserActions")[0].props;
  await actionsProps.onStatusChange(actionsProps.user);
  await harness.flushAsync();
  assert.equal(directoryCallbackCount, 0, "Failed changeStatus must not invoke onDirectoryChanged");
  assert.equal(harness.stateSlots[3], "Simulated PATCH failure");

  // 3. Failed changeAllowedIp
  const ipSaved = await actionsProps.onAllowedIpChange(actionsProps.user, "203.0.113.88");
  await harness.flushAsync();
  assert.equal(ipSaved, false, "Failed changeAllowedIp must resolve to false");
  assert.equal(directoryCallbackCount, 0, "Failed changeAllowedIp must not invoke onDirectoryChanged");
  assert.equal(harness.stateSlots[3], "Simulated PATCH failure");

  // 4. Failed deleteUser
  actionsProps.onDelete(actionsProps.user);
  tree = harness.render();
  harness.findNodes(tree, (n) => n.type === "input" && n.props?.autoFocus === true)[0].props.onChange({
    target: { value: "alice@example.com" },
  });
  tree = harness.render();
  harness.findNodes(tree, (n) => n.type === "button" && harness.textOf(n).includes("Delete customer"))[0].props.onClick();
  await harness.flushAsync();
  assert.equal(directoryCallbackCount, 0, "Failed deleteUser must not invoke onDirectoryChanged");
  assert.equal(harness.stateSlots[3], "Simulated DELETE failure");
  assert.equal(harness.stateSlots[0].length, 1, "Failed deleteUser must keep customer in state");
});

test("AdminUsersPanel isolates synchronous callback throws and asynchronous callback rejections across all four mutations", async () => {
  for (const mode of ["sync-throw", "async-reject"]) {
    let callbackInvocations = 0;
    const directoryUsers = [
      {
        id: "cust-1",
        email: "alice@example.com",
        role: "customer",
        status: "active",
        allowed_ip: "203.0.113.10",
        created_at: "2026-11-01T00:00:00Z",
      },
    ];

    const harness = createPanelHarness({
      onDirectoryChanged: () => {
        callbackInvocations += 1;
        if (mode === "sync-throw") {
          throw new Error("Synchronous callback failure");
        }
        return Promise.reject(new Error("Asynchronous callback rejection"));
      },
      fetchResponder: async (_url, method) => {
        if (method === "GET") {
          return { ok: true, status: 200, json: async () => ({ users: directoryUsers.map((u) => ({ ...u })) }) };
        }
        return { ok: true, status: method === "DELETE" ? 204 : 200, json: async () => ({}) };
      },
    });

    // Load initial users
    let tree = harness.render();
    harness.findNodes(tree, (n) => n.type === "button" && harness.textOf(n).includes("Refresh list"))[0].props.onClick();
    await harness.flushAsync();

    // 1. createUser with throwing/rejecting callback
    tree = harness.render();
    harness.findNodes(tree, (n) => n.type === "button" && harness.textOf(n).includes("Create customer"))[0].props.onClick();
    tree = harness.render();
    harness.findNodes(tree, (n) => n.type === "input" && n.props?.placeholder === "customer@example.com")[0].props.onChange({
      target: { value: "new@example.com" },
    });
    harness.findNodes(tree, (n) => n.type === "input" && n.props?.placeholder === "At least 8 characters")[0].props.onChange({
      target: { value: "SecretPass123!" },
    });
    harness.findNodes(tree, (n) => n.type === "input" && n.props?.placeholder === "Customer's public IPv4 or IPv6")[0].props.onChange({
      target: { value: "203.0.113.77" },
    });
    tree = harness.render();
    await harness.findNodes(tree, (n) => n.type === "form")[0].props.onSubmit({ preventDefault() {} });
    await harness.flushAsync();
    assert.equal(callbackInvocations, 1);
    assert.equal(harness.stateSlots[3], null, `createUser error must remain null on ${mode}`);
    assert.equal(harness.stateSlots[4], "Created the account for new@example.com.");

    // 2. changeStatus with throwing/rejecting callback
    tree = harness.render();
    const actionsProps = harness.findNodes(tree, (n) => typeof n.type === "function" && n.type.name === "UserActions")[0].props;
    await actionsProps.onStatusChange(actionsProps.user);
    await harness.flushAsync();
    assert.equal(callbackInvocations, 2);
    assert.equal(harness.stateSlots[3], null, `changeStatus error must remain null on ${mode}`);
    assert.equal(harness.stateSlots[4], "alice@example.com login paused.");

    // 3. changeAllowedIp with throwing/rejecting callback
    const saved = await actionsProps.onAllowedIpChange(actionsProps.user, "203.0.113.88");
    await harness.flushAsync();
    assert.equal(saved, true, `changeAllowedIp must still return true on ${mode}`);
    assert.equal(callbackInvocations, 3);
    assert.equal(harness.stateSlots[3], null, `changeAllowedIp error must remain null on ${mode}`);
    assert.equal(harness.stateSlots[4], "Allowed IP updated for alice@example.com.");

    // 4. deleteUser with throwing/rejecting callback
    actionsProps.onDelete(actionsProps.user);
    tree = harness.render();
    harness.findNodes(tree, (n) => n.type === "input" && n.props?.autoFocus === true)[0].props.onChange({
      target: { value: "alice@example.com" },
    });
    tree = harness.render();
    harness.findNodes(tree, (n) => n.type === "button" && harness.textOf(n).includes("Delete customer"))[0].props.onClick();
    await harness.flushAsync();
    assert.equal(callbackInvocations, 4);
    assert.equal(harness.stateSlots[3], null, `deleteUser error must remain null on ${mode}`);
    assert.equal(harness.stateSlots[4], "Deleted the account for alice@example.com.");
  }
});
