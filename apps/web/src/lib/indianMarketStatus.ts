/**
 * Official Indian Standard Time (IST / Asia/Kolkata) Clock & NSE/BSE Equity Market Status Engine.
 *
 * Design guarantees:
 * 1. Timezone-independent: Always computes IST (UTC+05:30 / Asia/Kolkata) regardless of the visitor's local system timezone.
 * 2. Official NSE/BSE Regular Equity Session: Monday to Friday, 09:15:00 to 15:30:00 IST (09:15 inclusive, 15:30 exclusive).
 * 3. Holiday-aware: Accounts for official NSE/BSE equity trading holidays across 2025, 2026, and 2027.
 * 4. Special-session-aware: Accounts for special trading sessions including Diwali Muhurat Trading windows.
 * 5. Safe fallback: Returns "MARKET STATUS UNAVAILABLE" if the clock timestamp is invalid or outside verified calendar bounds
 *    without a verified backend status override, never falsely claiming the market is live.
 */

export type MarketStatusState = "OPEN" | "CLOSED" | "UNAVAILABLE";

export type MarketStatusLabel =
  | "INDIAN MARKET LIVE"
  | "INDIAN MARKET CLOSED"
  | "MARKET STATUS UNAVAILABLE";

export type MarketSessionKind =
  | "REGULAR_TRADING"
  | "MUHURAT_TRADING"
  | "SPECIAL_TRADING"
  | "PRE_OPEN"
  | "POST_CLOSE"
  | "WEEKEND"
  | "HOLIDAY"
  | "UNAVAILABLE";

export interface SpecialTradingSession {
  /** YYYY-MM-DD in IST */
  dateIst: string;
  /** Session name (e.g., "Diwali Laxmi Pujan — Muhurat Trading") */
  name: string;
  /** Session kind */
  kind: "MUHURAT_TRADING" | "SPECIAL_TRADING";
  /** Opening time in minutes from 00:00 IST (e.g., 18:00 = 1080) */
  openMinuteOfDay: number;
  /** Closing time in minutes from 00:00 IST (e.g., 19:00 = 1140) */
  closeMinuteOfDay: number;
}

export interface IstClockSnapshot {
  /** Formatted 12-hour time with AM/PM and IST suffix, e.g. "05:30:42 AM IST" */
  time12hWithZone: string;
  /** Formatted 24-hour time with IST suffix, e.g. "05:30:42 IST" */
  time24hWithZone: string;
  /** Uppercase full date string, e.g. "THURSDAY, 05 NOVEMBER 2026" */
  dateHeadingUppercase: string;
  /** ISO-style IST date key YYYY-MM-DD */
  dateKeyIst: string;
  /** Numeric components in IST */
  year: number;
  month: number;
  day: number;
  weekdayIndex: number; // 0 = Sunday .. 6 = Saturday
  weekdayLong: string;
  hours24: number;
  minutes: number;
  seconds: number;
  /** Total seconds elapsed since 00:00:00 IST today */
  secondsOfDay: number;
  /** Underlying epoch milliseconds used */
  epochMs: number;
}

export interface MarketCountdownInfo {
  /** Target event type */
  targetEvent: "CLOSE" | "OPEN";
  /** Target IST date key YYYY-MM-DD */
  targetDateIst: string;
  /** Target time label in IST, e.g. "03:30 PM IST" or "09:15 AM IST" */
  targetTimeLabelIst: string;
  /** Total remaining seconds until target event */
  remainingSeconds: number;
  /** Formatted countdown string, e.g. "03h 51m 22s" or "2d 17h 44m 22s" */
  formattedCountdown: string;
  /** Human-readable summary, e.g. "Opens in 03h 51m 22s (Today, 09:15 AM IST)" */
  summaryText: string;
}

export interface IndianMarketStatusResult {
  state: MarketStatusState;
  label: MarketStatusLabel;
  isLive: boolean;
  dotColor: "emerald" | "rose" | "amber";
  sessionKind: MarketSessionKind;
  reason: string;
  holidayName: string | null;
  specialSessionName: string | null;
  scheduleSummary: string;
  countdown: MarketCountdownInfo | null;
  istClock: IstClockSnapshot | null;
}

export interface EvaluateMarketStatusOptions {
  /** Optional server-clock offset in milliseconds (serverUtcMs - clientUtcMs) */
  serverTimeOffsetMs?: number;
  /** Optional explicit flag if clock/status source is known to be unavailable */
  forceUnavailable?: boolean;
  /** Optional custom holiday map override for testing */
  holidaysOverride?: Record<string, string>;
  /** Optional custom special sessions override for testing */
  specialSessionsOverride?: Record<string, SpecialTradingSession>;
}

/** Fixed IST offset: UTC + 5 hours 30 minutes (330 minutes = 19,800,000 ms). India has no DST. */
export const IST_OFFSET_MINUTES = 330;
export const IST_OFFSET_MS = IST_OFFSET_MINUTES * 60 * 1000;

/** Official NSE/BSE Regular Equity Session: 09:15 AM to 03:30 PM IST */
export const NSE_REGULAR_OPEN_MINUTE = 9 * 60 + 15; // 555 (09:15)
export const NSE_REGULAR_CLOSE_MINUTE = 15 * 60 + 30; // 930 (15:30)
export const NSE_REGULAR_OPEN_SECOND = NSE_REGULAR_OPEN_MINUTE * 60; // 33,300
export const NSE_REGULAR_CLOSE_SECOND = NSE_REGULAR_CLOSE_MINUTE * 60; // 55,800

/** Supported calendar year bounds for verified offline holiday schedule */
export const MIN_SUPPORTED_CALENDAR_YEAR = 2025;
export const MAX_SUPPORTED_CALENDAR_YEAR = 2027;

/**
 * Official NSE/BSE Equity Trading Holidays (2025–2027).
 * Keyed by IST calendar date (YYYY-MM-DD) -> Official Holiday Name.
 * Note: Dates with a special Muhurat Trading session are also listed in NSE_SPECIAL_SESSIONS
 * so the market opens strictly during the Muhurat window and remains closed outside it.
 */
export const NSE_TRADING_HOLIDAYS: Readonly<Record<string, string>> = Object.freeze({
  // 2025 NSE/BSE Holidays
  "2025-02-26": "Mahashivratri",
  "2025-03-14": "Holi",
  "2025-03-31": "Id-Ul-Fitr (Ramzan Id)",
  "2025-04-10": "Shri Mahavir Jayanti",
  "2025-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
  "2025-04-18": "Good Friday",
  "2025-05-01": "Maharashtra Day",
  "2025-08-15": "Independence Day",
  "2025-08-27": "Ganesh Chaturthi",
  "2025-10-02": "Mahatma Gandhi Jayanti / Dussehra",
  "2025-10-21": "Diwali Laxmi Pujan",
  "2025-10-22": "Diwali Balipratipada",
  "2025-11-05": "Prakash Gurpurb Sri Guru Nanak Dev",
  "2025-12-25": "Christmas",

  // 2026 NSE/BSE Holidays
  "2026-01-26": "Republic Day",
  "2026-03-03": "Holi",
  "2026-03-26": "Shri Ram Navami",
  "2026-03-31": "Shri Mahavir Jayanti",
  "2026-04-03": "Good Friday",
  "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
  "2026-05-01": "Maharashtra Day",
  "2026-05-28": "Bakri Id (Eid al-Adha)",
  "2026-06-26": "Muharram",
  "2026-09-14": "Ganesh Chaturthi",
  "2026-10-02": "Mahatma Gandhi Jayanti",
  "2026-10-20": "Dussehra",
  "2026-11-09": "Diwali Laxmi Pujan (Regular Session Holiday)",
  "2026-11-10": "Diwali Balipratipada",
  "2026-11-24": "Prakash Gurpurb Sri Guru Nanak Dev",
  "2026-12-25": "Christmas",

  // 2027 NSE/BSE Holidays
  "2027-01-26": "Republic Day",
  "2027-03-10": "Id-Ul-Fitr (Ramzan Id)",
  "2027-03-22": "Holi",
  "2027-03-26": "Good Friday",
  "2027-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
  "2027-04-15": "Shri Ram Navami",
  "2027-05-17": "Bakri Id (Eid al-Adha)",
  "2027-08-16": "Parsi New Year",
  "2027-09-04": "Ganesh Chaturthi",
  "2027-10-11": "Dussehra",
  "2027-10-29": "Diwali Laxmi Pujan",
  "2027-11-15": "Prakash Gurpurb Sri Guru Nanak Dev",
});

/**
 * Official Special / Muhurat Trading Sessions on NSE/BSE.
 * During these windows, the market is OPEN even on a holiday or weekend.
 */
export const NSE_SPECIAL_SESSIONS: Readonly<Record<string, SpecialTradingSession>> =
  Object.freeze({
    "2025-10-21": {
      dateIst: "2025-10-21",
      name: "Diwali Muhurat Trading Session",
      kind: "MUHURAT_TRADING",
      openMinuteOfDay: 13 * 60 + 45, // 13:45 IST (01:45 PM IST)
      closeMinuteOfDay: 14 * 60 + 45, // 14:45 IST (02:45 PM IST)
    },
    "2026-11-08": {
      dateIst: "2026-11-08",
      name: "Diwali Laxmi Pujan Muhurat Trading Session",
      kind: "MUHURAT_TRADING",
      openMinuteOfDay: 18 * 60, // 18:00 IST (06:00 PM IST)
      closeMinuteOfDay: 19 * 60, // 19:00 IST (07:00 PM IST)
    },
    "2027-10-29": {
      dateIst: "2027-10-29",
      name: "Diwali Laxmi Pujan Muhurat Trading Session",
      kind: "MUHURAT_TRADING",
      openMinuteOfDay: 18 * 60, // 18:00 IST (06:00 PM IST)
      closeMinuteOfDay: 19 * 60, // 19:00 IST (07:00 PM IST)
    },
  });

const WEEKDAY_NAMES_UPPER = [
  "SUNDAY",
  "MONDAY",
  "TUESDAY",
  "WEDNESDAY",
  "THURSDAY",
  "FRIDAY",
  "SATURDAY",
] as const;

const WEEKDAY_NAMES_SHORT = [
  "Sun",
  "Mon",
  "Tue",
  "Wed",
  "Thu",
  "Fri",
  "Sat",
] as const;

const MONTH_NAMES_UPPER = [
  "JANUARY",
  "FEBRUARY",
  "MARCH",
  "APRIL",
  "MAY",
  "JUNE",
  "JULY",
  "AUGUST",
  "SEPTEMBER",
  "OCTOBER",
  "NOVEMBER",
  "DECEMBER",
] as const;

const MONTH_NAMES_SHORT = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
] as const;

function pad2(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

export function formatMinuteOfDay12h(minuteOfDay: number): string {
  const clamped = Math.max(0, Math.min(1439, Math.floor(minuteOfDay)));
  const h24 = Math.floor(clamped / 60);
  const m = clamped % 60;
  const period = h24 >= 12 ? "PM" : "AM";
  const h12 = h24 % 12 === 0 ? 12 : h24 % 12;
  return `${pad2(h12)}:${pad2(m)} ${period} IST`;
}

/**
 * Compute an exact IST (UTC+05:30) clock snapshot from any Date or epoch millisecond value.
 * Uses pure UTC millisecond arithmetic shifted by +05:30 (+19,800,000 ms) so that it produces
 * identical output regardless of the visitor's browser/OS timezone setting.
 */
export function getIstClockSnapshot(
  input: Date | number | string = Date.now(),
  serverTimeOffsetMs = 0,
): IstClockSnapshot | null {
  let rawMs: number;
  if (typeof input === "number") {
    rawMs = input;
  } else if (input instanceof Date) {
    rawMs = input.getTime();
  } else if (typeof input === "string" && input.trim().length > 0) {
    rawMs = new Date(input).getTime();
  } else {
    return null;
  }

  if (!Number.isFinite(rawMs) || !Number.isFinite(serverTimeOffsetMs)) {
    return null;
  }

  const effectiveEpochMs = Math.round(rawMs + serverTimeOffsetMs);
  // Reasonable sanity check: reject dates before 2000 or after 2100
  if (effectiveEpochMs < 946684800000 || effectiveEpochMs > 4102444800000) {
    return null;
  }

  const istShiftedDate = new Date(effectiveEpochMs + IST_OFFSET_MS);
  const year = istShiftedDate.getUTCFullYear();
  const month = istShiftedDate.getUTCMonth() + 1; // 1..12
  const day = istShiftedDate.getUTCDate(); // 1..31
  const weekdayIndex = istShiftedDate.getUTCDay(); // 0=Sun..6=Sat
  const hours24 = istShiftedDate.getUTCHours();
  const minutes = istShiftedDate.getUTCMinutes();
  const seconds = istShiftedDate.getUTCSeconds();

  const period = hours24 >= 12 ? "PM" : "AM";
  const hours12 = hours24 % 12 === 0 ? 12 : hours24 % 12;

  const time12hWithZone = `${pad2(hours12)}:${pad2(minutes)}:${pad2(seconds)} ${period} IST`;
  const time24hWithZone = `${pad2(hours24)}:${pad2(minutes)}:${pad2(seconds)} IST`;
  const weekdayLong = WEEKDAY_NAMES_UPPER[weekdayIndex] ?? "MONDAY";
  const monthLong = MONTH_NAMES_UPPER[month - 1] ?? "JANUARY";
  const dateHeadingUppercase = `${weekdayLong}, ${pad2(day)} ${monthLong} ${year}`;
  const dateKeyIst = `${year}-${pad2(month)}-${pad2(day)}`;
  const secondsOfDay = hours24 * 3600 + minutes * 60 + seconds;

  return {
    time12hWithZone,
    time24hWithZone,
    dateHeadingUppercase,
    dateKeyIst,
    year,
    month,
    day,
    weekdayIndex,
    weekdayLong,
    hours24,
    minutes,
    seconds,
    secondsOfDay,
    epochMs: effectiveEpochMs,
  };
}

/**
 * Format a duration in seconds into a crisp countdown string, e.g. "03h 51m 22s" or "2d 17h 45m 00s".
 */
export function formatCountdownDuration(totalSeconds: number): string {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds));
  const days = Math.floor(safeSeconds / 86400);
  const remAfterDays = safeSeconds % 86400;
  const hours = Math.floor(remAfterDays / 3600);
  const remAfterHours = remAfterDays % 3600;
  const minutes = Math.floor(remAfterHours / 60);
  const seconds = remAfterHours % 60;

  if (days > 0) {
    return `${days}d ${pad2(hours)}h ${pad2(minutes)}m ${pad2(seconds)}s`;
  }
  return `${pad2(hours)}h ${pad2(minutes)}m ${pad2(seconds)}s`;
}

interface DaySessionWindow {
  dateKeyIst: string;
  openSecondOfDay: number;
  closeSecondOfDay: number;
  openMinuteOfDay: number;
  closeMinuteOfDay: number;
  kind: "REGULAR_TRADING" | "MUHURAT_TRADING" | "SPECIAL_TRADING";
  specialName: string | null;
}

function getDaySessionWindow(
  year: number,
  month: number,
  day: number,
  weekdayIndex: number,
  holidays: Readonly<Record<string, string>>,
  specialSessions: Readonly<Record<string, SpecialTradingSession>>,
): DaySessionWindow | null {
  const dateKeyIst = `${year}-${pad2(month)}-${pad2(day)}`;
  const special = specialSessions[dateKeyIst];
  if (special) {
    return {
      dateKeyIst,
      openSecondOfDay: special.openMinuteOfDay * 60,
      closeSecondOfDay: special.closeMinuteOfDay * 60,
      openMinuteOfDay: special.openMinuteOfDay,
      closeMinuteOfDay: special.closeMinuteOfDay,
      kind: special.kind,
      specialName: special.name,
    };
  }

  // Weekend check (0 = Sunday, 6 = Saturday)
  if (weekdayIndex === 0 || weekdayIndex === 6) {
    return null;
  }

  // Official NSE/BSE holiday check
  if (holidays[dateKeyIst]) {
    return null;
  }

  return {
    dateKeyIst,
    openSecondOfDay: NSE_REGULAR_OPEN_SECOND,
    closeSecondOfDay: NSE_REGULAR_CLOSE_SECOND,
    openMinuteOfDay: NSE_REGULAR_OPEN_MINUTE,
    closeMinuteOfDay: NSE_REGULAR_CLOSE_MINUTE,
    kind: "REGULAR_TRADING",
    specialName: null,
  };
}

function findNextOpeningCountdown(
  clock: IstClockSnapshot,
  holidays: Readonly<Record<string, string>>,
  specialSessions: Readonly<Record<string, SpecialTradingSession>>,
): MarketCountdownInfo | null {
  // Check if there is still an upcoming session today
  const todayWindow = getDaySessionWindow(
    clock.year,
    clock.month,
    clock.day,
    clock.weekdayIndex,
    holidays,
    specialSessions,
  );

  if (todayWindow && clock.secondsOfDay < todayWindow.openSecondOfDay) {
    const remainingSeconds = todayWindow.openSecondOfDay - clock.secondsOfDay;
    const targetTimeLabelIst = formatMinuteOfDay12h(todayWindow.openMinuteOfDay);
    const formattedCountdown = formatCountdownDuration(remainingSeconds);
    return {
      targetEvent: "OPEN",
      targetDateIst: clock.dateKeyIst,
      targetTimeLabelIst,
      remainingSeconds,
      formattedCountdown,
      summaryText: `Opens in ${formattedCountdown} (Today, ${targetTimeLabelIst})`,
    };
  }

  // Otherwise scan up to 14 calendar days ahead in IST
  const baseMidnightIstAsUtcMs = Date.UTC(clock.year, clock.month - 1, clock.day, 0, 0, 0);
  for (let daysAhead = 1; daysAhead <= 14; daysAhead += 1) {
    const candidateMs = baseMidnightIstAsUtcMs + daysAhead * 86400 * 1000;
    const candidateDate = new Date(candidateMs);
    const cYear = candidateDate.getUTCFullYear();
    const cMonth = candidateDate.getUTCMonth() + 1;
    const cDay = candidateDate.getUTCDate();
    const cWeekday = candidateDate.getUTCDay();

    const candidateWindow = getDaySessionWindow(
      cYear,
      cMonth,
      cDay,
      cWeekday,
      holidays,
      specialSessions,
    );

    if (candidateWindow) {
      const remainingSeconds =
        (daysAhead - 1) * 86400 +
        (86400 - clock.secondsOfDay) +
        candidateWindow.openSecondOfDay;
      const targetTimeLabelIst = formatMinuteOfDay12h(candidateWindow.openMinuteOfDay);
      const formattedCountdown = formatCountdownDuration(remainingSeconds);
      const dayLabel =
        daysAhead === 1
          ? "Tomorrow"
          : `${WEEKDAY_NAMES_SHORT[cWeekday]}, ${pad2(cDay)} ${MONTH_NAMES_SHORT[cMonth - 1]}`;
      return {
        targetEvent: "OPEN",
        targetDateIst: candidateWindow.dateKeyIst,
        targetTimeLabelIst,
        remainingSeconds,
        formattedCountdown,
        summaryText: `Next open in ${formattedCountdown} (${dayLabel}, ${targetTimeLabelIst})`,
      };
    }
  }

  return null;
}

/**
 * Evaluate the official NSE/BSE Indian Stock Market status for a given timestamp.
 * Completely separated from React UI rendering so it can be unit-tested and reused across components.
 */
export function evaluateIndianMarketStatus(
  input: Date | number | string = Date.now(),
  options: EvaluateMarketStatusOptions = {},
): IndianMarketStatusResult {
  if (options.forceUnavailable) {
    return {
      state: "UNAVAILABLE",
      label: "MARKET STATUS UNAVAILABLE",
      isLive: false,
      dotColor: "amber",
      sessionKind: "UNAVAILABLE",
      reason: "Live market schedule verification is temporarily unavailable.",
      holidayName: null,
      specialSessionName: null,
      scheduleSummary: "NSE/BSE Regular Equity Session: Mon–Fri, 09:15 AM – 03:30 PM IST",
      countdown: null,
      istClock: null,
    };
  }

  const clock = getIstClockSnapshot(input, options.serverTimeOffsetMs ?? 0);
  if (!clock) {
    return {
      state: "UNAVAILABLE",
      label: "MARKET STATUS UNAVAILABLE",
      isLive: false,
      dotColor: "amber",
      sessionKind: "UNAVAILABLE",
      reason: "Unable to resolve a valid Asia/Kolkata (IST) timestamp.",
      holidayName: null,
      specialSessionName: null,
      scheduleSummary: "NSE/BSE Regular Equity Session: Mon–Fri, 09:15 AM – 03:30 PM IST",
      countdown: null,
      istClock: null,
    };
  }

  // If year is outside our verified 2025–2027 NSE/BSE holiday calendar and no custom override was supplied,
  // report MARKET STATUS UNAVAILABLE rather than guessing holiday status.
  if (
    !options.holidaysOverride &&
    (clock.year < MIN_SUPPORTED_CALENDAR_YEAR || clock.year > MAX_SUPPORTED_CALENDAR_YEAR)
  ) {
    return {
      state: "UNAVAILABLE",
      label: "MARKET STATUS UNAVAILABLE",
      isLive: false,
      dotColor: "amber",
      sessionKind: "UNAVAILABLE",
      reason: `NSE/BSE holiday calendar for ${clock.year} is not verified in offline bundle.`,
      holidayName: null,
      specialSessionName: null,
      scheduleSummary: "NSE/BSE Regular Equity Session: Mon–Fri, 09:15 AM – 03:30 PM IST",
      countdown: null,
      istClock: clock,
    };
  }

  const holidays = options.holidaysOverride ?? NSE_TRADING_HOLIDAYS;
  const specialSessions = options.specialSessionsOverride ?? NSE_SPECIAL_SESSIONS;

  const holidayName = holidays[clock.dateKeyIst] ?? null;
  const specialSession = specialSessions[clock.dateKeyIst] ?? null;

  const todayWindow = getDaySessionWindow(
    clock.year,
    clock.month,
    clock.day,
    clock.weekdayIndex,
    holidays,
    specialSessions,
  );

  // Case 1: Today has an active trading window (regular weekday or special Muhurat session)
  if (todayWindow) {
    if (
      clock.secondsOfDay >= todayWindow.openSecondOfDay &&
      clock.secondsOfDay < todayWindow.closeSecondOfDay
    ) {
      const remainingSeconds = todayWindow.closeSecondOfDay - clock.secondsOfDay;
      const targetTimeLabelIst = formatMinuteOfDay12h(todayWindow.closeMinuteOfDay);
      const formattedCountdown = formatCountdownDuration(remainingSeconds);

      const isSpecial = todayWindow.kind !== "REGULAR_TRADING";
      const reason = isSpecial
        ? `${todayWindow.specialName ?? "Special Trading Session"} is live on NSE & BSE.`
        : "NSE & BSE regular equity session is active (09:15 AM – 03:30 PM IST).";

      return {
        state: "OPEN",
        label: "INDIAN MARKET LIVE",
        isLive: true,
        dotColor: "emerald",
        sessionKind: todayWindow.kind,
        reason,
        holidayName,
        specialSessionName: todayWindow.specialName,
        scheduleSummary: isSpecial
          ? `${todayWindow.specialName}: ${formatMinuteOfDay12h(todayWindow.openMinuteOfDay)} – ${targetTimeLabelIst}`
          : "NSE/BSE Regular Equity Session: Mon–Fri, 09:15 AM – 03:30 PM IST",
        countdown: {
          targetEvent: "CLOSE",
          targetDateIst: clock.dateKeyIst,
          targetTimeLabelIst,
          remainingSeconds,
          formattedCountdown,
          summaryText: `Closes in ${formattedCountdown} (${targetTimeLabelIst})`,
        },
        istClock: clock,
      };
    }

    // Today has a window, but current time is before open or after close
    const nextOpenCountdown = findNextOpeningCountdown(clock, holidays, specialSessions);
    const isBeforeOpen = clock.secondsOfDay < todayWindow.openSecondOfDay;
    const isSpecial = todayWindow.kind !== "REGULAR_TRADING";

    let reason: string;
    if (isSpecial) {
      reason = isBeforeOpen
        ? `Regular session closed (${holidayName ?? "Special Day"}). ${todayWindow.specialName} opens at ${formatMinuteOfDay12h(todayWindow.openMinuteOfDay)}.`
        : `${todayWindow.specialName} has concluded for today.`;
    } else {
      reason = isBeforeOpen
        ? "Pre-open hours — NSE & BSE regular equity session opens at 09:15 AM IST."
        : "Post-close hours — NSE & BSE regular equity session closed at 03:30 PM IST.";
    }

    return {
      state: "CLOSED",
      label: "INDIAN MARKET CLOSED",
      isLive: false,
      dotColor: "rose",
      sessionKind: isBeforeOpen ? "PRE_OPEN" : "POST_CLOSE",
      reason,
      holidayName,
      specialSessionName: todayWindow.specialName,
      scheduleSummary: "NSE/BSE Regular Equity Session: Mon–Fri, 09:15 AM – 03:30 PM IST",
      countdown: nextOpenCountdown,
      istClock: clock,
    };
  }

  // Case 2: Today has no trading window (Weekend or Official NSE/BSE Holiday)
  const nextOpenCountdown = findNextOpeningCountdown(clock, holidays, specialSessions);
  const isWeekend = clock.weekdayIndex === 0 || clock.weekdayIndex === 6;

  const reason = holidayName
    ? `NSE & BSE closed for official trading holiday: ${holidayName}.`
    : `Weekend market closure (${clock.weekdayLong.charAt(0) + clock.weekdayLong.slice(1).toLowerCase()}). Regular trading runs Monday–Friday, 09:15 AM – 03:30 PM IST.`;

  return {
    state: "CLOSED",
    label: "INDIAN MARKET CLOSED",
    isLive: false,
    dotColor: "rose",
    sessionKind: holidayName && !isWeekend ? "HOLIDAY" : "WEEKEND",
    reason,
    holidayName,
    specialSessionName: specialSession?.name ?? null,
    scheduleSummary: "NSE/BSE Regular Equity Session: Mon–Fri, 09:15 AM – 03:30 PM IST",
    countdown: nextOpenCountdown,
    istClock: clock,
  };
}
