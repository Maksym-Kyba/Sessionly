# Google OAuth Frontend Integration

This document describes the backend contract for the frontend implementation. The frontend must
not receive Google credentials, authorization codes, PKCE verifiers, ID tokens, access tokens, or
the backend session token.

## Sign-in

1. Start sign-in with a top-level browser navigation to
   `GET ${NEXT_PUBLIC_API_URL}/api/v1/auth/google/start`. The current frontend already exports
   this URL as `GOOGLE_SIGN_IN_URL` in `frontend/src/config/api.ts`.
2. The backend sets a short-lived HttpOnly browser-binding cookie, redirects to Google, and handles
   the callback at the configured `GOOGLE_REDIRECT_URI`.
3. On success, the backend sets an HttpOnly session cookie and redirects to
   `FRONTEND_AUTH_SUCCESS_URL`. On failure or cancellation it redirects to
   `FRONTEND_AUTH_ERROR_URL` with a generic `auth_error` query value. Redirect destinations must
   be exact entries in `FRONTEND_AUTH_REDIRECT_ALLOWLIST`; there is no client-supplied return URL.
4. On application load, request `GET /api/v1/accounts/me` with browser credentials included. A 200
   response means the psychologist is signed in; a 401 means no valid session. The response
   includes `csrf_token`.

Example browser navigation:

```ts
window.location.assign(GOOGLE_SIGN_IN_URL);
```

## Authenticated API calls

Include credentials on requests to the backend, for example:

```ts
fetch(`${API_BASE_URL}/api/v1/accounts/me/availability-rules`, {
  credentials: "include",
});
```

For POST, PUT, PATCH, and DELETE requests, include both the exact frontend `Origin` (the browser
sets it) and `X-CSRF-Token` using the value returned by `/api/v1/accounts/me`. Refresh the value by
calling `/accounts/me` after a page reload; keep it in memory and never store it as a session
credential. Requests without a valid session or CSRF token are rejected.

Psychologists can update their public display name and scheduling time zone with
`PATCH /api/v1/accounts/me`. Send only the fields being changed; `display_name` must be non-blank
and no longer than 200 characters, and `time_zone` must be a valid IANA time-zone identifier.
Explicit `null` values are rejected. The response uses the same shape as `GET /api/v1/accounts/me`,
including the refreshed `csrf_token`.

Example request:

```json
{
  "display_name": "Dr. Example",
  "time_zone": "Europe/Kyiv"
}
```

Call `POST /api/v1/auth/logout` with `credentials: "include"` and the CSRF header. The backend
revokes the current session and clears the HttpOnly cookie.

Public profile and availability routes do not require credentials. The current
`GET /api/v1/psychologists/{public_id}` response contains `public_id`, `display_name`, `time_zone`,
`session_duration_minutes`, `price_minor`, and `currency`. The last three fields are populated only
when all future published availability slots share the same duration, price, and currency; otherwise
all three are `null`. Each availability slot also returns its own price and currency.

## Origins and cookies

- Local development: frontend `http://localhost:3000`, backend `http://localhost:8000`; set
  `credentials: "include"`. The local session and OAuth browser-binding cookies use
  `SameSite=Lax` and `Secure=false`. Their paths are narrowed to `/api/v1` and
  `/api/v1/auth/google`, so they are not sent to the Next.js root pages on the shared `localhost`
  hostname.
- Production HTTPS: the cookie is `HttpOnly`, `Secure`, `Path=/`, has no `Domain`, and uses the
  `__Host-sessionly_session` default name. The default `SameSite=Lax` assumes frontend and backend
  are same-site (same registrable domain). If they are cross-site, deployment must configure
  `SameSite=None; Secure` and the frontend must confirm that browser third-party-cookie policies
  permit the chosen topology.
- Backend CORS must list the exact frontend origin and allow credentials plus `X-CSRF-Token`.
  Wildcard origins are not supported.

The frontend team must confirm the success and error routes, production origins, and behavior for
the generic `account_unavailable`, `sign_in_cancelled`, and `oauth_failed` query values before
deployment.

New psychologist profiles use the verified Google `name` claim. If it is absent, first-login
profile creation is rejected rather than exposing the email local part as a public name. The initial
time zone is `DEFAULT_PSYCHOLOGIST_TIME_ZONE` (default `Europe/Kyiv`). Confirm whether the frontend
needs a profile-edit flow before the demo; no profile-update endpoint is included in this backend
scope.

Do not log callback query strings: OAuth `code` and `state` arrive on the backend callback URL.
The production proxy/access-log configuration must redact or omit that query string.
