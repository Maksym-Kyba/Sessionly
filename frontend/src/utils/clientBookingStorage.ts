/**
 * Browser storage for the client booking flow. Clients have no accounts, so the flow keeps a few
 * short-lived values in the browser:
 *
 * - The selected slot survives the email round trip in `localStorage`, because the verification
 *   link usually opens in a new tab, where `sessionStorage` would be empty. It contains no client
 *   email and expires after one hour.
 * - The one-time booking verification grant stays in `sessionStorage` for the current tab only, so
 *   the client can choose another slot if the selected one was taken meanwhile.
 * - The client access token of each booking is kept in `localStorage` so that the client can return
 *   to the booking page from the same browser. It is also kept in memory, so that the redirect to
 *   the booking page works in the same tab even when storage is unavailable.
 *
 * Every access is wrapped in try/catch because storage may be unavailable (private mode, blocked
 * site data); the flow then degrades gracefully instead of failing.
 */

const PENDING_SELECTION_KEY = "sessionly.pendingSelection";
const GRANT_KEY = "sessionly.verificationGrant";
const BOOKING_ACCESS_PREFIX = "sessionly.bookingAccess.";
const PENDING_RECOVERY_KEY = "sessionly.pendingRecovery";

/** Matches the one-hour upper bound for keeping a slot selection while the client checks email. */
const PENDING_SELECTION_TTL_MS = 60 * 60 * 1000;

/** The slot a client selected before requesting the verification email. */
export type PendingSelection = {
  psychologistPublicId: string;
  psychologistName: string;
  timeZone: string;
  slotId: string;
  startsAt: string;
  endsAt: string;
  priceMinor: number;
  currency: string;
  /** Generated once per selection so that retries replay the same booking request. */
  idempotencyKey: string;
  savedAt: number;
};

/** A booking verification grant kept for the current tab. */
export type StoredGrant = {
  token: string;
  expiresAt: string;
  psychologistPublicId: string;
};

/** Client access to one booking, plus display context the booking endpoint does not return. */
export type StoredBookingAccess = {
  token: string;
  expiresAt: string | null;
  psychologistPublicId: string;
  psychologistName: string;
  timeZone: string;
};

function read<T>(storage: () => Storage, key: string): T | null {
  try {
    const raw = storage().getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

/** Returns `false` when storage is unavailable and the value was not persisted. */
function write(storage: () => Storage, key: string, value: unknown): boolean {
  try {
    storage().setItem(key, JSON.stringify(value));
    return true;
  } catch {
    // Storage is unavailable; the flow continues without persistence.
    return false;
  }
}

function remove(storage: () => Storage, key: string): void {
  try {
    storage().removeItem(key);
  } catch {
    // Storage is unavailable; nothing to remove.
  }
}

const local = () => window.localStorage;
const session = () => window.sessionStorage;

export function savePendingSelection(selection: Omit<PendingSelection, "savedAt">): void {
  write(local, PENDING_SELECTION_KEY, { ...selection, savedAt: Date.now() });
}

/** Returns the pending selection, discarding it when it is older than one hour. */
export function loadPendingSelection(): PendingSelection | null {
  const selection = read<PendingSelection>(local, PENDING_SELECTION_KEY);
  if (!selection) return null;
  if (Date.now() - selection.savedAt > PENDING_SELECTION_TTL_MS) {
    remove(local, PENDING_SELECTION_KEY);
    return null;
  }
  return selection;
}

export function clearPendingSelection(): void {
  remove(local, PENDING_SELECTION_KEY);
}

export function saveGrant(grant: StoredGrant): void {
  write(session, GRANT_KEY, grant);
}

/** Returns the stored grant for a psychologist when it has not expired yet. */
export function loadGrant(psychologistPublicId: string): StoredGrant | null {
  const grant = read<StoredGrant>(session, GRANT_KEY);
  if (!grant || grant.psychologistPublicId !== psychologistPublicId) return null;
  if (new Date(grant.expiresAt).getTime() <= Date.now()) {
    remove(session, GRANT_KEY);
    return null;
  }
  return grant;
}

export function clearGrant(): void {
  remove(session, GRANT_KEY);
}

/**
 * Booking access kept for the lifetime of this tab's JavaScript, which survives client-side
 * navigation but not a page reload. `persisted` records whether `localStorage` also holds it.
 */
const memoryAccess = new Map<string, { access: StoredBookingAccess; persisted: boolean }>();

/** Stores booking access; returns `false` when it could only be kept in memory for this tab. */
export function saveBookingAccess(bookingId: string, access: StoredBookingAccess): boolean {
  const persisted = write(local, BOOKING_ACCESS_PREFIX + bookingId, access);
  memoryAccess.set(bookingId, { access, persisted });
  return persisted;
}

/** `true` when this tab holds the booking access only in memory, so a reload would lose it. */
export function isBookingAccessMemoryOnly(bookingId: string): boolean {
  return memoryAccess.get(bookingId)?.persisted === false;
}

export function loadBookingAccess(bookingId: string): StoredBookingAccess | null {
  const access =
    memoryAccess.get(bookingId)?.access ??
    read<StoredBookingAccess>(local, BOOKING_ACCESS_PREFIX + bookingId);
  if (!access) return null;
  if (access.expiresAt && new Date(access.expiresAt).getTime() <= Date.now()) {
    remove(local, BOOKING_ACCESS_PREFIX + bookingId);
    memoryAccess.delete(bookingId);
    return null;
  }
  return access;
}

/**
 * A booking that was created but whose access token never reached this browser (for example, the
 * response was lost and the retry replayed the booking without a token). The client verifies the
 * email again, and the verification page then recovers access with the fresh grant.
 */
export type PendingRecovery = {
  bookingId: string;
  psychologistPublicId: string;
  psychologistName: string;
  timeZone: string;
  savedAt: number;
};

export function savePendingRecovery(recovery: Omit<PendingRecovery, "savedAt">): void {
  write(local, PENDING_RECOVERY_KEY, { ...recovery, savedAt: Date.now() });
}

/** Returns the pending recovery, discarding it when it is older than one hour. */
export function loadPendingRecovery(): PendingRecovery | null {
  const recovery = read<PendingRecovery>(local, PENDING_RECOVERY_KEY);
  if (!recovery) return null;
  if (Date.now() - recovery.savedAt > PENDING_SELECTION_TTL_MS) {
    remove(local, PENDING_RECOVERY_KEY);
    return null;
  }
  return recovery;
}

export function clearPendingRecovery(): void {
  remove(local, PENDING_RECOVERY_KEY);
}

/** Generates an `Idempotency-Key` value of 32 hexadecimal characters. */
export function newIdempotencyKey(): string {
  const bytes = new Uint8Array(16);
  window.crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}
