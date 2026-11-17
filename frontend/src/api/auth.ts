import { API_BASE_URL } from "@/config/api";

/** The signed-in psychologist as returned by `GET /api/v1/accounts/me`. */
export type CurrentPsychologist = {
  public_id: string;
  display_name: string;
  email: string | null;
  time_zone: string;
  /** Sent in the `X-CSRF-Token` header of state-changing requests. Kept in memory only. */
  csrf_token: string;
};

/**
 * Returns the signed-in psychologist, or `null` when there is no valid session.
 * The session itself is an HttpOnly cookie that the browser sends automatically.
 */
export async function getCurrentPsychologist(): Promise<CurrentPsychologist | null> {
  const response = await fetch(`${API_BASE_URL}/api/v1/accounts/me`, {
    credentials: "include",
    cache: "no-store",
  });
  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`Unexpected response from /accounts/me: ${response.status}`);
  }
  return (await response.json()) as CurrentPsychologist;
}

/** Ends the current session on the backend, which also removes the session cookie. */
export async function signOut(csrfToken: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/logout`, {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": csrfToken },
  });
  if (!response.ok && response.status !== 401) {
    throw new Error(`Unexpected response from /auth/logout: ${response.status}`);
  }
}
