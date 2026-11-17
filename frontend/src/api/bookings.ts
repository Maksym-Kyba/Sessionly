import { API_BASE_URL } from "@/config/api";

/** Booking statuses returned by the backend. An elapsed `HELD` booking is reported as `EXPIRED`. */
export type BookingStatus = "HELD" | "CONFIRMED" | "EXPIRED";

/** One booking as returned by `GET /api/v1/accounts/me/bookings`. */
export type PsychologistBooking = {
  id: string;
  /** Typed as `string` as well, so that statuses added later on the backend do not break parsing. */
  status: BookingStatus | string;
  /** UTC ISO 8601 timestamps. */
  starts_at: string;
  ends_at: string;
  /** Sensitive client data: display only, never log. */
  client_email: string | null;
  session_duration_minutes: number;
  /** Price in minor units (kopiykas). */
  price_minor: number;
  currency: string;
  created_at: string;
};

/** A page of bookings, ordered by `starts_at` ascending. */
export type PsychologistBookingPage = {
  items: PsychologistBooking[];
  /** Number of all bookings belonging to the psychologist, before pagination. */
  total: number;
  limit: number;
  offset: number;
};

/** Raised when the backend rejects the request because the session is missing or expired. */
export class BookingsUnauthorizedError extends Error {}

/**
 * Returns a page of the signed-in psychologist's bookings.
 * The session itself is an HttpOnly cookie that the browser sends automatically.
 */
export async function listMyBookings(limit = 100, offset = 0): Promise<PsychologistBookingPage> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  const response = await fetch(`${API_BASE_URL}/api/v1/accounts/me/bookings?${query}`, {
    credentials: "include",
    cache: "no-store",
  });
  if (response.status === 401) {
    throw new BookingsUnauthorizedError("Psychologist session is missing or expired");
  }
  if (!response.ok) {
    throw new Error(`Unexpected response from /accounts/me/bookings: ${response.status}`);
  }
  return (await response.json()) as PsychologistBookingPage;
}
