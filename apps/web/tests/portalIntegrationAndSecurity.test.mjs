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
    const compiled = babel.transformSync(src, {
      filename: full,
      presets: [
        requireWithFallback("@babel/preset-typescript"),
        [requireWithFallback("@babel/preset-react"), { runtime: "automatic" }],
      ],
    });
    assert.ok(compiled && compiled.code && compiled.code.length > 0, `Failed to compile ${rel}`);
  }
});
