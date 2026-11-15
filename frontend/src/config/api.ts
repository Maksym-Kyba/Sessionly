/** Base URL of the Sessionly backend API. */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Backend route that starts the psychologist Google OAuth sign-in (see docs/API_CONTRACT.md). */
export const GOOGLE_SIGN_IN_URL = `${API_BASE_URL}/api/v1/auth/google/start`;
