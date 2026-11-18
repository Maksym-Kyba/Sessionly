/** Display locale for all client-facing dates and prices. */
const LOCALE = "uk-UA";

/** Formats a price given in minor units (for example kopiykas) as a currency amount. */
export function formatPrice(priceMinor: number, currency: string): string {
  return new Intl.NumberFormat(LOCALE, {
    style: "currency",
    currency,
    minimumFractionDigits: priceMinor % 100 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(priceMinor / 100);
}

/** Returns the calendar date of an instant in a time zone as `YYYY-MM-DD`, for grouping. */
export function dayKey(isoInstant: string, timeZone: string): string {
  // The en-CA locale formats dates as YYYY-MM-DD.
  return new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(isoInstant));
}

/** Formats an instant as a weekday and date, for example "понеділок, 23 листопада". */
export function formatDay(isoInstant: string, timeZone: string): string {
  return new Intl.DateTimeFormat(LOCALE, {
    timeZone,
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(new Date(isoInstant));
}

/** Formats an instant as a 24-hour time, for example "14:30". */
export function formatTime(isoInstant: string, timeZone: string): string {
  return new Intl.DateTimeFormat(LOCALE, {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(isoInstant));
}

/** Formats a slot interval, for example "понеділок, 23 листопада, 14:00–14:50". */
export function formatSlot(startsAt: string, endsAt: string, timeZone: string): string {
  return `${formatDay(startsAt, timeZone)}, ${formatTime(startsAt, timeZone)}–${formatTime(endsAt, timeZone)}`;
}

/** Formats a remaining duration in milliseconds as `mm:ss`. */
export function formatCountdown(remainingMs: number): string {
  const totalSeconds = Math.max(0, Math.ceil(remainingMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

/** Legacy IANA names that some browsers still report, mapped to their current names. */
const LEGACY_TIME_ZONES: Record<string, string> = {
  "Europe/Kiev": "Europe/Kyiv",
  "Europe/Uzhgorod": "Europe/Kyiv",
  "Europe/Zaporozhye": "Europe/Kyiv",
};

/** Returns the current IANA name for a time zone, replacing legacy aliases such as `Europe/Kiev`. */
export function canonicalTimeZone(timeZone: string): string {
  return LEGACY_TIME_ZONES[timeZone] ?? timeZone;
}

/** Returns the browser time zone under its current name, or `null` when it cannot be determined. */
export function browserTimeZone(): string | null {
  try {
    const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return timeZone ? canonicalTimeZone(timeZone) : null;
  } catch {
    return null;
  }
}
