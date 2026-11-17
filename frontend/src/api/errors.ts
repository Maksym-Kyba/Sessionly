/**
 * Error raised when the backend answers with a non-success status.
 * The message intentionally contains only the route and status, never request data or tokens.
 */
export class ApiError extends Error {
  readonly status: number;

  constructor(route: string, status: number) {
    super(`Unexpected response from ${route}: ${status}`);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Returns the HTTP status of an `ApiError`, or `null` for network and other failures. */
export function errorStatus(error: unknown): number | null {
  return error instanceof ApiError ? error.status : null;
}
