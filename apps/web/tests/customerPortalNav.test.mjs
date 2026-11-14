import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (relativePath) => fs.readFileSync(path.join(webRoot, relativePath), "utf8");

test("customer terminal provides account and sign-out navigation", () => {
  const nav = read("src/components/customer/CustomerPortalNav.tsx");
  const terminal = read("src/app/terminal/page.tsx");

  assert.match(nav, /aria-label="Customer account navigation"/);
  assert.match(nav, /href="\/account"/);
  assert.match(nav, /onClick=\{\(\) => void signOut\(\)\}/);
  assert.match(terminal, /<CustomerPortalNav\s*\/>/);
});

test("customer account page keeps IP restrictions admin-managed and supports return navigation", () => {
  const account = read("src/app/account/page.tsx");

  assert.match(account, /href="\/terminal"/);
  assert.match(account, /network access rule is enforced by the API and managed by an administrator/i);
  assert.match(account, /autoComplete="current-password"/);
  assert.equal((account.match(/autoComplete="new-password"/g) ?? []).length, 2);
});
