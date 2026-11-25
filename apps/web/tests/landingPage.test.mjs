import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import ts from "typescript";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const webRoot = path.resolve(__dirname, "..");

function compileWithTypeScript(source, fullPath) {
  const result = ts.transpileModule(source, {
    fileName: fullPath,
    reportDiagnostics: true,
    compilerOptions: {
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  });
  const errors = (result.diagnostics ?? [])
    .filter((diagnostic) => diagnostic.category === ts.DiagnosticCategory.Error)
    .map((diagnostic) => ts.flattenDiagnosticMessageText(diagnostic.messageText, "\n"));
  assert.deepEqual(errors, [], `TypeScript transpilation failed for ${fullPath}`);
  return result.outputText;
}

function loadTsModule(relPath) {
  const fullPath = path.join(webRoot, relPath);
  const code = fs.readFileSync(fullPath, "utf8");
  const transformed = compileWithTypeScript(code, fullPath);
  const exportsObj = {};
  const moduleObj = { exports: exportsObj };
  const sandbox = {
    exports: exportsObj,
    module: moduleObj,
    require: () => {
      throw new Error("Unexpected external import in the market-status module.");
    },
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
  vm.runInNewContext(transformed, sandbox, { filename: fullPath });
  return moduleObj.exports;
}

const indianMarketStatus = loadTsModule("src/lib/indianMarketStatus.ts");

test("Live IST Clock: formats exact HH:MM:SS AM/PM IST and uppercase date in Asia/Kolkata regardless of visitor timezone", () => {
  const snap = indianMarketStatus.getIstClockSnapshot("2026-11-05T00:00:42Z");
  assert.ok(snap);
  assert.equal(snap.time12hWithZone, "05:30:42 AM IST");
  assert.equal(snap.time24hWithZone, "05:30:42 IST");
  assert.equal(snap.dateHeadingUppercase, "THURSDAY, 05 NOVEMBER 2026");
  assert.equal(snap.dateKeyIst, "2026-11-05");
  assert.equal(snap.hours24, 5);
  assert.equal(snap.minutes, 30);
  assert.equal(snap.seconds, 42);

  const pmSnap = indianMarketStatus.getIstClockSnapshot("2026-11-05T08:35:09Z");
  assert.ok(pmSnap);
  assert.equal(pmSnap.time12hWithZone, "02:05:09 PM IST");
  assert.equal(pmSnap.time24hWithZone, "14:05:09 IST");
  assert.equal(pmSnap.dateHeadingUppercase, "THURSDAY, 05 NOVEMBER 2026");

  const midnightSnap = indianMarketStatus.getIstClockSnapshot("2026-11-04T18:30:00Z");
  assert.ok(midnightSnap);
  assert.equal(midnightSnap.time12hWithZone, "12:00:00 AM IST");
  assert.equal(midnightSnap.dateHeadingUppercase, "THURSDAY, 05 NOVEMBER 2026");

  const noonSnap = indianMarketStatus.getIstClockSnapshot("2026-11-05T06:30:00Z");
  assert.ok(noonSnap);
  assert.equal(noonSnap.time12hWithZone, "12:00:00 PM IST");
});

test("Live IST Clock: applies serverTimeOffsetMs accurately when device clock is skewed", () => {
  const baseMs = new Date("2026-11-05T00:00:00Z").getTime();
  const calibrated = indianMarketStatus.getIstClockSnapshot(baseMs, 42_000);
  assert.ok(calibrated);
  assert.equal(calibrated.time12hWithZone, "05:30:42 AM IST");
});

test("NSE Market Status: regular weekday pre-open, exact open (09:15), active session, and exact close (15:30)", () => {
  const preOpen = indianMarketStatus.evaluateIndianMarketStatus(
    "2026-11-05T05:23:38+05:30",
  );
  assert.equal(preOpen.state, "CLOSED");
  assert.equal(preOpen.label, "NSE MARKET CLOSED");
  assert.equal(preOpen.isLive, false);
  assert.equal(preOpen.dotColor, "rose");
  assert.equal(preOpen.sessionKind, "PRE_OPEN");
  assert.ok(preOpen.countdown);
  assert.equal(preOpen.countdown.targetEvent, "OPEN");
  assert.equal(preOpen.countdown.targetDateIst, "2026-11-05");
  assert.equal(preOpen.countdown.targetTimeLabelIst, "09:15 AM IST");
  assert.equal(preOpen.countdown.remainingSeconds, 13882);
  assert.equal(preOpen.countdown.formattedCountdown, "03h 51m 22s");

  const oneSecBeforeOpen = indianMarketStatus.evaluateIndianMarketStatus(
    "2026-11-05T09:14:59+05:30",
  );
  assert.equal(oneSecBeforeOpen.state, "CLOSED");
  assert.equal(oneSecBeforeOpen.label, "NSE MARKET CLOSED");
  assert.equal(oneSecBeforeOpen.isLive, false);
  assert.equal(oneSecBeforeOpen.countdown.remainingSeconds, 1);

  const exactOpen = indianMarketStatus.evaluateIndianMarketStatus(
    "2026-11-05T09:15:00+05:30",
  );
  assert.equal(exactOpen.state, "OPEN");
  assert.equal(exactOpen.label, "NSE MARKET LIVE");
  assert.equal(exactOpen.isLive, true);
  assert.equal(exactOpen.dotColor, "emerald");
  assert.equal(exactOpen.sessionKind, "REGULAR_TRADING");
  assert.ok(exactOpen.countdown);
  assert.equal(exactOpen.countdown.targetEvent, "CLOSE");
  assert.equal(exactOpen.countdown.targetTimeLabelIst, "03:30 PM IST");
  assert.equal(exactOpen.countdown.remainingSeconds, 22500);

  const lastSecOpen = indianMarketStatus.evaluateIndianMarketStatus(
    "2026-11-05T15:29:59+05:30",
  );
  assert.equal(lastSecOpen.state, "OPEN");
  assert.equal(lastSecOpen.label, "NSE MARKET LIVE");
  assert.equal(lastSecOpen.isLive, true);
  assert.equal(lastSecOpen.countdown.remainingSeconds, 1);

  const exactClose = indianMarketStatus.evaluateIndianMarketStatus(
    "2026-11-05T15:30:00+05:30",
  );
  assert.equal(exactClose.state, "CLOSED");
  assert.equal(exactClose.label, "NSE MARKET CLOSED");
  assert.equal(exactClose.isLive, false);
  assert.equal(exactClose.dotColor, "rose");
  assert.equal(exactClose.sessionKind, "POST_CLOSE");
  assert.ok(exactClose.countdown);
  assert.equal(exactClose.countdown.targetEvent, "OPEN");
  assert.equal(exactClose.countdown.targetDateIst, "2026-11-06");
  assert.equal(exactClose.countdown.remainingSeconds, 63900);
});

test("NSE Market Status: weekends, published NSE holidays, and the announced Diwali Muhurat session", () => {
  const saturday = indianMarketStatus.evaluateIndianMarketStatus(
    "2026-11-14T11:00:00+05:30",
  );
  assert.equal(saturday.state, "CLOSED");
  assert.equal(saturday.label, "NSE MARKET CLOSED");
  assert.equal(saturday.isLive, false);
  assert.equal(saturday.sessionKind, "WEEKEND");
  assert.ok(saturday.countdown);
  assert.equal(saturday.countdown.targetDateIst, "2026-11-16");
  assert.equal(saturday.countdown.targetTimeLabelIst, "09:15 AM IST");

  const republicDay = indianMarketStatus.evaluateIndianMarketStatus(
    "2026-01-26T10:30:00+05:30",
  );
  assert.equal(republicDay.state, "CLOSED");
  assert.equal(republicDay.label, "NSE MARKET CLOSED");
  assert.equal(republicDay.isLive, false);
  assert.equal(republicDay.sessionKind, "HOLIDAY");
  assert.equal(republicDay.holidayName, "Republic Day");
  assert.ok(republicDay.countdown);
  assert.equal(republicDay.countdown.targetDateIst, "2026-01-27");

  const addedNseHoliday = indianMarketStatus.evaluateIndianMarketStatus(
    "2026-01-15T11:00:00+05:30",
  );
  assert.equal(addedNseHoliday.state, "CLOSED");
  assert.equal(addedNseHoliday.sessionKind, "HOLIDAY");
  assert.match(addedNseHoliday.holidayName, /Municipal Corporation Election/);

  const guruNanakHoliday = indianMarketStatus.evaluateIndianMarketStatus(
    "2026-11-24T11:00:00+05:30",
  );
  assert.equal(guruNanakHoliday.state, "CLOSED");
  assert.equal(guruNanakHoliday.label, "NSE MARKET CLOSED");
  assert.equal(guruNanakHoliday.sessionKind, "HOLIDAY");
  assert.match(guruNanakHoliday.holidayName, /Guru Nanak/);
  assert.equal(guruNanakHoliday.countdown.targetDateIst, "2026-11-25");

  const beforeMuhurat = indianMarketStatus.evaluateIndianMarketStatus(
    "2026-11-08T12:00:00+05:30",
  );
  assert.equal(beforeMuhurat.state, "CLOSED");
  assert.equal(beforeMuhurat.label, "NSE MARKET CLOSED");
  assert.equal(beforeMuhurat.countdown.targetDateIst, "2026-11-08");
  assert.equal(beforeMuhurat.countdown.targetTimeLabelIst, "02:20 PM IST");

  const duringMuhurat = indianMarketStatus.evaluateIndianMarketStatus(
    "2026-11-08T14:30:00+05:30",
  );
  assert.equal(duringMuhurat.state, "OPEN");
  assert.equal(duringMuhurat.label, "NSE MARKET LIVE");
  assert.equal(duringMuhurat.isLive, true);
  assert.equal(duringMuhurat.sessionKind, "MUHURAT_TRADING");
  assert.equal(duringMuhurat.countdown.targetEvent, "CLOSE");
  assert.equal(duringMuhurat.countdown.targetTimeLabelIst, "03:40 PM IST");
  assert.equal(duringMuhurat.countdown.remainingSeconds, 70 * 60);

  const afterMuhurat = indianMarketStatus.evaluateIndianMarketStatus(
    "2026-11-08T15:45:00+05:30",
  );
  assert.equal(afterMuhurat.state, "CLOSED");
  assert.equal(afterMuhurat.label, "NSE MARKET CLOSED");
  assert.equal(afterMuhurat.countdown.targetDateIst, "2026-11-09");
  assert.equal(afterMuhurat.countdown.targetTimeLabelIst, "09:15 AM IST");
});

test("NSE Market Status: returns MARKET STATUS UNAVAILABLE when invalid and gives an estimate beyond the verified calendar", () => {
  const forced = indianMarketStatus.evaluateIndianMarketStatus(Date.now(), {
    forceUnavailable: true,
  });
  assert.equal(forced.state, "UNAVAILABLE");
  assert.equal(forced.label, "MARKET STATUS UNAVAILABLE");
  assert.equal(forced.isLive, false);
  assert.equal(forced.dotColor, "amber");

  const invalidDate = indianMarketStatus.evaluateIndianMarketStatus("not-a-valid-date");
  assert.equal(invalidDate.state, "UNAVAILABLE");
  assert.equal(invalidDate.label, "MARKET STATUS UNAVAILABLE");
  assert.equal(invalidDate.isLive, false);

  const unverifiedFutureYear = indianMarketStatus.evaluateIndianMarketStatus(
    "2027-05-12T10:30:00+05:30",
  );
  assert.equal(unverifiedFutureYear.state, "ESTIMATE");
  assert.equal(unverifiedFutureYear.label, "NSE SCHEDULE ESTIMATE");
  assert.equal(unverifiedFutureYear.countdown.targetEvent, "CLOSE");
  const verified = indianMarketStatus.evaluateIndianMarketStatus("2027-05-12T10:30:00+05:30", {
    calendar: { holidays: { "2027-05-12": "Fixture holiday" }, verifiedYears: [2027] },
  });
  assert.equal(verified.state, "CLOSED");
  assert.equal(verified.holidayName, "Fixture holiday");
  assert.equal(unverifiedFutureYear.isLive, false);

  const laterYear = indianMarketStatus.evaluateIndianMarketStatus(
    "2032-05-12T10:30:00+05:30",
  );
  assert.equal(laterYear.state, "ESTIMATE");
  assert.equal(laterYear.label, "NSE SCHEDULE ESTIMATE");
});

test("Landing Page & How It Works page compile cleanly and describe the current rule engine accurately", () => {
  const landingFiles = [
    "src/lib/indianMarketStatus.ts",
    "src/components/landing/LiveIstClock.tsx",
    "src/components/landing/IndianMarketStatusBadge.tsx",
    "src/components/landing/ScrollReveal.tsx",
    "src/components/landing/BullBearHeroArena.tsx",
    "src/components/landing/LandingPage.tsx",
    "src/components/landing/WhatWeDonePage.tsx",
    "src/app/page.tsx",
    "src/app/what-we-done/page.tsx",
    "src/app/terminal/page.tsx",
    "src/app/login/page.tsx",
    "src/app/account/page.tsx",
    "src/app/admin/login/page.tsx",
    "src/app/admin/page.tsx",
    "src/components/auth/DashboardAccessGate.tsx",
  ];

  for (const rel of landingFiles) {
    const fullPath = path.join(webRoot, rel);
    assert.equal(fs.existsSync(fullPath), true, `Expected ${rel} to exist`);
    const source = fs.readFileSync(fullPath, "utf8");
    const result = compileWithTypeScript(source, fullPath);
    assert.ok(result.length > 0, `Failed to compile ${rel}`);
  }

  // Strictly verify ZERO proprietary indicator names are disclosed on any public landing page component
  const publicWebsiteFiles = [
    "src/components/landing/BullBearHeroArena.tsx",
    "src/components/landing/LandingPage.tsx",
    "src/components/landing/WhatWeDonePage.tsx",
    "src/app/what-we-done/page.tsx",
  ];
  const forbiddenIndicatorPattern =
    /\b(UT\s*Bot|ut_bot|EMA|RSI|MACD|Supertrend|supertrend|ATR|ROC|Wilder|Heikin[\s-]*Ashi)\b/i;

  for (const rel of publicWebsiteFiles) {
    const content = fs.readFileSync(path.join(webRoot, rel), "utf8");
    assert.doesNotMatch(
      content,
      forbiddenIndicatorPattern,
      `Forbidden indicator name disclosed in ${rel}`,
    );
  }

  const landingSrc = fs.readFileSync(
    path.join(webRoot, "src/components/landing/LandingPage.tsx"),
    "utf8",
  );
  assert.match(landingSrc, /href="\/login"/);
  assert.match(landingSrc, /href="\/what-we-done"/);
  assert.match(landingSrc, /href="\/admin\/login"/);
  assert.match(landingSrc, /How It Works/);
  assert.doesNotMatch(landingSrc, /What We Done/);
  assert.match(landingSrc, /Customer Sign In/);
  assert.match(landingSrc, /Explore how the analysis works/);
  assert.match(landingSrc, /ILLUSTRATIVE TERMINAL SIMULATION/);
  assert.match(landingSrc, /NOT LIVE MARKET PRICES/);

  const heroArenaSrc = fs.readFileSync(
    path.join(webRoot, "src/components/landing/BullBearHeroArena.tsx"),
    "utf8",
  );
  assert.match(heroArenaSrc, /ILLUSTRATIVE FIVE-CHECK SIGNAL VIEW/);
  assert.match(heroArenaSrc, /NOT LIVE/);
  assert.doesNotMatch(heroArenaSrc, /AI AGENTS|5M IST FEED|live candlestick depth grid/i);

  const whatWeDoneSrc = fs.readFileSync(
    path.join(webRoot, "src/components/landing/WhatWeDonePage.tsx"),
    "utf8",
  );
  assert.match(whatWeDoneSrc, /How It Works/);
  assert.match(whatWeDoneSrc, /broker orders are placed/);
  assert.match(whatWeDoneSrc, /SIGNAL CHECK 01/);
  assert.match(whatWeDoneSrc, /SIGNAL CHECK 02/);
  assert.match(whatWeDoneSrc, /SIGNAL CHECK 03/);
  assert.match(whatWeDoneSrc, /SIGNAL CHECK 04/);
  assert.match(whatWeDoneSrc, /SIGNAL CHECK 05/);
  assert.match(whatWeDoneSrc, /When to BUY/);
  assert.match(whatWeDoneSrc, /When to SELL/);
  assert.match(whatWeDoneSrc, /not independent AI agents/);
  assert.match(whatWeDoneSrc, /does not calculate account-specific position size/);

  for (const unsupportedPath of [
    "apps/api/app/signals/market_context.py",
    "apps/api/app/signals/ai_analysis.py",
    "apps/api/app/signals/risk_manager.py",
    "apps/web/src/lib/marketData.ts",
  ]) {
    assert.ok(
      !landingSrc.includes(unsupportedPath),
      `Landing page refers to a source file missing from current main: ${unsupportedPath}`,
    );
  }

  const terminalPageSrc = fs.readFileSync(
    path.join(webRoot, "src/app/terminal/page.tsx"),
    "utf8",
  );
  assert.match(terminalPageSrc, /DashboardAccessGate/);
});
