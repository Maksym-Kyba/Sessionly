import { ApiError } from "@/api/errors";
import { API_BASE_URL } from "@/config/api";

/** Public psychologist profile as returned by `GET /api/v1/psychologists/{public_id}`. */
export type PublicPsychologist = {
  public_id: string;
  display_name: string;
  /** IANA time zone used for scheduling and display. */
  time_zone: string;
  session_duration_minutes: number | null;
  /** Price in minor currency units (kopiykas for UAH). */
  price_minor: number | null;
  currency: string | null;
};

/** One bookable slot from `GET /api/v1/psychologists/{public_id}/availability`. */
export type AvailabilitySlot = {
  id: string;
  starts_at: string;
  ends_at: string;
  price_minor: number;
  currency: string;
  state: "available";
};

export type PublicAvailability = {
  psychologist_id: string;
  time_zone: string;
  slots: AvailabilitySlot[];
};

/** One-time booking verification grant returned after a verification link is consumed. */
export type VerificationGrant = {
  status: "verified";
  booking_verification_token: string;
  expires_at: string;
  psychologist_public_id: string;
};

const JSON_HEADERS = { "Content-Type": "application/json" };

/** Returns the public profile of a psychologist, or `null` when the public ID is unknown. */
export async function getPublicPsychologist(publicId: string): Promise<PublicPsychologist | null> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/psychologists/${encodeURIComponent(publicId)}`,
    { cache: "no-store" },
  );
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new ApiError("/psychologists/{public_id}", response.status);
  }
  return (await response.json()) as PublicPsychologist;
}

/**
 * Returns the available slots of a psychologist in the half-open range `[from, to)`.
 * The backend accepts ranges of at most 30 days.
 */
export async function getPublicAvailability(
  publicId: string,
  from: Date,
  to: Date,
): Promise<PublicAvailability> {
  const query = new URLSearchParams({ from: from.toISOString(), to: to.toISOString() });
  const response = await fetch(
    `${API_BASE_URL}/api/v1/psychologists/${encodeURIComponent(publicId)}/availability?${query}`,
    { cache: "no-store" },
  );
  if (!response.ok) {
    throw new ApiError("/psychologists/{public_id}/availability", response.status);
  }
  return (await response.json()) as PublicAvailability;
}

/**
 * Asks the backend to email a one-time verification link to the client.
 * The backend answers with the same generic acceptance for every valid request.
 */
export async function requestEmailVerification(
  email: string,
  psychologistPublicId: string,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/email-verifications`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ email, psychologist_public_id: psychologistPublicId }),
  });
  if (!response.ok) {
    throw new ApiError("/email-verifications", response.status);
  }
}

/** Exchanges a verification-link token for a one-time booking verification grant. */
export async function consumeEmailVerification(token: string): Promise<VerificationGrant> {
  const response = await fetch(`${API_BASE_URL}/api/v1/email-verifications/consume`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ token }),
  });
  if (!response.ok) {
    throw new ApiError("/email-verifications/consume", response.status);
  }
  return (await response.json()) as VerificationGrant;
}
