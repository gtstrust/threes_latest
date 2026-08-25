/**
 * The API client's error handling, which is the only branchy logic in it.
 *
 * FastAPI does not have one error shape: `HTTPException` gives a string detail,
 * a Pydantic failure gives a list of objects. Rendering the second one raw puts
 * "[object Object]" in front of a player standing on a tee, so both have to
 * become a sentence.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./env', () => ({
  env: {
    supabaseUrl: 'https://example.supabase.co',
    supabasePublishableKey: 'sb_publishable_test',
    apiBaseUrl: 'http://api.test',
  },
}));

const getAccessToken = vi.fn<() => Promise<string | null>>();
vi.mock('./supabase', () => ({ getAccessToken: () => getAccessToken() }));

const { api, ApiError } = await import('./api');

function respond(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => {
  getAccessToken.mockResolvedValue('a-token');
  vi.restoreAllMocks();
});

describe('authentication', () => {
  it('sends the access token as a bearer', async () => {
    const fetchMock = vi.fn().mockResolvedValue(respond(200, { status: 'ok' }));
    vi.stubGlobal('fetch', fetchMock);

    await api.get('/tournaments');

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://api.test/tournaments');
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer a-token');
  });

  it('fails before making a request when signed out', async () => {
    // Distinct from a 401: there is no token to be rejected. Sending the request
    // anyway would turn "signed out" into a server round trip and a confusing
    // error, and would hit the API once per screen for a user who cannot use it.
    getAccessToken.mockResolvedValue(null);
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await expect(api.get('/tournaments')).rejects.toThrow(ApiError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does not attach a token to the health check', async () => {
    const fetchMock = vi.fn().mockResolvedValue(respond(200, { status: 'ok' }));
    vi.stubGlobal('fetch', fetchMock);

    await api.health();

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });
});

describe('error shapes', () => {
  it('passes through a plain HTTPException detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        respond(409, {
          detail: "A round can't be drawn while the tournament is CREATED.",
        }),
      ),
    );

    await expect(api.post('/tournaments/x/rounds')).rejects.toMatchObject({
      status: 409,
      detail: "A round can't be drawn while the tournament is CREATED.",
    });
  });

  it('flattens a Pydantic validation list into a sentence', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        respond(422, {
          detail: [
            { loc: ['body', 'status'], msg: "Input should be 'CREATED'", type: 'enum' },
            { loc: ['body', 'hole_numbers'], msg: 'A loop is 3 holes', type: 'value_error' },
          ],
        }),
      ),
    );

    await expect(api.post('/x')).rejects.toMatchObject({
      status: 422,
      detail: "status: Input should be 'CREATED'; hole_numbers: A loop is 3 holes",
    });
  });

  it('falls back to the status text when the body is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('<html>502</html>', { status: 502 })),
    );

    await expect(api.get('/x')).rejects.toMatchObject({ status: 502 });
  });

  it('surfaces a 503 as itself, so callers can retry rather than sign out', async () => {
    // The backend answers 503 when it cannot reach Supabase to verify a token.
    // The session is usually fine; treating it as an auth failure would send a
    // player back through a magic link over somebody else's outage.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(respond(503, { detail: 'Could not reach Supabase' })),
    );

    await expect(api.get('/players/me')).rejects.toMatchObject({ status: 503 });
  });
});

describe('bodies', () => {
  it('returns undefined for a body-less success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));

    await expect(api.delete('/tournaments/x/participants/y')).resolves.toBeUndefined();
  });
});
