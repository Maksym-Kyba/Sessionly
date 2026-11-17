import { ApiError } from "@/api/errors";
import { API_BASE_URL } from "@/config/api";

/** Booking lifecycle statuses owned by the backend `booking` module. */
export type BookingStatus = "HELD" | "CONFIRMED" | "EXPIRED";

/** Booking snapshot visible to the client, as returned by `GET /api/v1/bookings/{id}`. */
export type ClientBooking = {
  id: string;
  status: BookingStatus;
  starts_at: string;
  ends_at: string;
  session_duration_minutes: number;
  /** Price in minor currency units (kopiykas for UAH). */
  price_minor: number;
  currency: string;
  created_at: string;
  hold_expires_at: string;
};

/** Response of `POST /api/v1/bookings`. */
export type CreatedBooking = ClientBooking & {
  slot_id: string;
  /** Returned only once; `null` when an idempotent replay reuses the same grant. */
  client_access_token: string | null;
  client_access_token_expires_at: string | null;
  idempotent_replay: boolean;
  payment_stage: string;
};

export type BookingAccessToken = {
  client_access_token: string;
  expires_at: string;
};

const JSON_HEADERS = { "Content-Type": "application/json" };

/**
 * Creates a 15-minute hold for a slot using a one-time booking verification grant.
 * Reusing the same `idempotencyKey` for the same slot safely replays the original result.
 */
export async function createBooking(
  slotId: string,
  bookingVerificationToken: string,
  idempotencyKey: string,
): Promise<CreatedBooking> {
  const response = await fetch(`${API_BASE_URL}/api/v1/bookings`, {
    method: "POST",
    headers: { ...JSON_HEADERS, "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({
      slot_id: slotId,
      booking_verification_token: bookingVerificationToken,
    }),
  });
  if (!response.ok) {
    throw new ApiError("/bookings", response.status);
  }
  return (await response.json()) as CreatedBooking;
}

/** Replaces a lost client access token using a fresh booking verification grant. */
export async function recoverBookingAccessToken(
  bookingId: string,
  bookingVerificationToken: string,
): Promise<BookingAccessToken> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/bookings/${encodeURIComponent(bookingId)}/access-token`,
    {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ booking_verification_token: bookingVerificationToken }),
    },
  );
  if (!response.ok) {
    throw new ApiError("/bookings/{id}/access-token", response.status);
  }
  return (await response.json()) as BookingAccessToken;
}

/**
 * Returns a booking for the client holding `accessToken`, or `null` when the booking is missing
 * or the token is invalid or expired (the backend answers both cases with 404).
 */
export async function getClientBooking(
  bookingId: string,
  accessToken: string,
): Promise<ClientBooking | null> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/bookings/${encodeURIComponent(bookingId)}`,
    {
      cache: "no-store",
      headers: { Authorization: `Bearer ${accessToken}` },
    },
  );
  if (response.status === 404 || response.status === 401) {
    return null;
  }
  if (!response.ok) {
    throw new ApiError("/bookings/{id}", response.status);
  }
  return (await response.json()) as ClientBooking;
}
