import { API_BASE_URL } from "@/config/api";

const RULES_URL = `${API_BASE_URL}/api/v1/accounts/me/availability-rules`;

/**
 * Request body of `POST` and `PUT /api/v1/accounts/me/availability-rules`.
 * Times are local wall-clock times (`HH:MM`) in the psychologist's IANA timezone.
 * The price is expressed in minor units (kopiykas).
 */
export type AvailabilityRuleInput = {
  /** Monday is 0 and Sunday is 6. */
  weekday: number;
  local_start: string;
  local_end: string;
  session_duration_minutes: number;
  price_minor: number;
  currency: "UAH";
  /** ISO date (`YYYY-MM-DD`). */
  valid_from: string;
  valid_until: string | null;
};

/** An availability rule as returned by the backend. */
export type AvailabilityRule = AvailabilityRuleInput & {
  id: string;
  psychologist_id: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** One entry of a FastAPI validation error response (HTTP 422). */
export type ValidationIssue = {
  loc: (string | number)[];
  msg: string;
  type: string;
};

/** Raised when the backend responds with a non-success status. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    /** The `detail` field of the response: a message or a list of validation issues. */
    readonly detail: string | ValidationIssue[] | null,
  ) {
    super(`Unexpected response from availability rules API: ${status}`);
    this.name = "ApiError";
  }
}

async function throwApiError(response: Response): Promise<never> {
  let detail: ApiError["detail"] = null;
  try {
    const body = (await response.json()) as { detail?: ApiError["detail"] };
    detail = body.detail ?? null;
  } catch {
    // The body is not JSON; the status code alone describes the error.
  }
  throw new ApiError(response.status, detail);
}

/** Lists the signed-in psychologist's active availability rules. */
export async function listAvailabilityRules(): Promise<AvailabilityRule[]> {
  const response = await fetch(RULES_URL, { credentials: "include", cache: "no-store" });
  if (!response.ok) {
    await throwApiError(response);
  }
  return (await response.json()) as AvailabilityRule[];
}

/** Creates an availability rule. */
export async function createAvailabilityRule(
  data: AvailabilityRuleInput,
  csrfToken: string,
): Promise<AvailabilityRule> {
  return sendRule(RULES_URL, "POST", data, csrfToken);
}

/** Replaces an existing availability rule. */
export async function updateAvailabilityRule(
  ruleId: string,
  data: AvailabilityRuleInput,
  csrfToken: string,
): Promise<AvailabilityRule> {
  return sendRule(`${RULES_URL}/${encodeURIComponent(ruleId)}`, "PUT", data, csrfToken);
}

/** Retires an availability rule. */
export async function deleteAvailabilityRule(ruleId: string, csrfToken: string): Promise<void> {
  const response = await fetch(`${RULES_URL}/${encodeURIComponent(ruleId)}`, {
    method: "DELETE",
    credentials: "include",
    headers: { "X-CSRF-Token": csrfToken },
  });
  if (!response.ok) {
    await throwApiError(response);
  }
}

async function sendRule(
  url: string,
  method: "POST" | "PUT",
  data: AvailabilityRuleInput,
  csrfToken: string,
): Promise<AvailabilityRule> {
  const response = await fetch(url, {
    method,
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    await throwApiError(response);
  }
  return (await response.json()) as AvailabilityRule;
}
