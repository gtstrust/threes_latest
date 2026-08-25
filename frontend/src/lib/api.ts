/**
 * The one way this app talks to its data (ADR-001).
 *
 * Every call carries the Supabase access token as a bearer, and FastAPI decides
 * what the caller may see. Nothing here knows about tournaments or scores — the
 * feature modules build on top.
 */

import { env } from './env';
import { getAccessToken } from './supabase';

/**
 * A failed request, carrying the status so callers can branch on it.
 *
 * The statuses that actually mean something in this API, and are worth handling
 * rather than showing raw:
 *
 * - **404 on `/players/me`** — a verified token does not imply a profile row.
 *   `ensureProfile` exists for this; see `features/auth`.
 * - **409** — a state-machine refusal (ADR-003/ADR-008), e.g. drawing a round
 *   before registration closes. The detail is written for a human; show it.
 * - **422** — the payload is wrong, most often a tie-break naming a player who
 *   is not tied (ADR-007).
 * - **503** — the backend could not reach Supabase to verify the token. The
 *   session is fine; retrying is the right response, not logging out.
 */
export class ApiError extends Error {
  // Declared rather than written as constructor parameter properties: the
  // tsconfig sets `erasableSyntaxOnly`, so type-directed syntax that emits
  // runtime code is rejected.
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

type Options = {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  body?: unknown;
  /** Sent unauthenticated. Only `/health` qualifies. */
  anonymous?: boolean;
};

async function request<T>(path: string, options: Options = {}): Promise<T> {
  const { method = 'GET', body, anonymous = false } = options;

  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  if (!anonymous) {
    const token = await getAccessToken();
    if (!token) {
      // Distinguished from a 401 on purpose: there is no token to be rejected,
      // so this is "you are signed out", not "your token was refused".
      throw new ApiError(401, 'Not signed in');
    }
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${env.apiBaseUrl}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response));
  }

  // 204, and any other body-less success.
  if (response.status === 204 || response.headers.get('content-length') === '0') {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/**
 * FastAPI's error shape, which is not one shape.
 *
 * `HTTPException` gives `{detail: "a sentence"}`, but a Pydantic validation
 * failure gives `{detail: [{loc, msg, type}, ...]}`. Rendering the second
 * directly puts `[object Object]` in front of a player standing on a tee, so
 * both are flattened to a sentence here rather than at each call site.
 */
async function readDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    const detail = body.detail;

    if (typeof detail === 'string') return detail;

    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          const entry = item as { loc?: unknown[]; msg?: string };
          const field = Array.isArray(entry.loc) ? entry.loc.slice(1).join('.') : '';
          return field ? `${field}: ${entry.msg}` : (entry.msg ?? 'Invalid value');
        })
        .join('; ');
    }
  } catch {
    // Not JSON — a proxy error page, say. Fall through to the status text.
  }
  return response.statusText || `Request failed with ${response.status}`;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PATCH', body }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  health: () => request<{ status: string }>('/health', { anonymous: true }),
};
