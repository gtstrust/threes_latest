"""The last thing between an unhandled exception and the browser.

Starlette builds its stack as `ServerErrorMiddleware` → user middleware (ours,
including CORS) → `ExceptionMiddleware` → routes. An exception nothing handles
travels *up past* `CORSMiddleware` to `ServerErrorMiddleware`, which writes the
500 itself — so that response never passes back down through the `send` wrapper
that adds `Access-Control-Allow-Origin`.

The result is a 500 the browser refuses to show. It reports
"blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present",
which sends the reader off to audit a CORS configuration that was correct all
along. That happened here, and cost an evening.

Registering `@app.exception_handler(Exception)` does **not** fix it: Starlette
special-cases the `Exception` and `500` keys and installs them on
`ServerErrorMiddleware`, which is still outside CORS. The handler has to be a
middleware *inside* the CORS one — see the registration order in `app/main.py`.
"""

import logging

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


class CatchUnhandledErrors:
    """Answer an unhandled exception with a 500 that still passes through CORS.

    Written as a pure ASGI middleware rather than a `BaseHTTPMiddleware`, which
    wraps the response in its own streaming machinery. ADR-010 depends on
    `BackgroundTasks` running after `get_db` commits, and `tests/test_realtime.py`
    pins that ordering; there is no reason to put anything in its way.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def guarded_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, guarded_send)
        except Exception:
            # Uvicorn logs unhandled exceptions only because they reach it. This
            # one stops here, so this call is the single record of it — without it
            # the failure is silent everywhere except the browser, which is
            # describing it wrongly.
            logger.exception(
                "Unhandled error on %s %s",
                scope.get("method", "?"),
                scope.get("path", "?"),
            )
            if started:
                # The status line is already on the wire; there is no response
                # left to replace. Let it fail as a broken response rather than
                # appending a second one.
                raise
            response = JSONResponse({"detail": "Internal Server Error"}, status_code=500)
            await response(scope, receive, send)
