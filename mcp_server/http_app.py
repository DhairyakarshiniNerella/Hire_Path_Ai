"""
Web (Streamable HTTP) entry point for the HirePath job MCP server.

The tools are the same ones server.py defines for STDIO; this file only wraps them
in a web app so the server can run as its own service (for example on Render):

    uvicorn --factory mcp_server.http_app:build_app --host 0.0.0.0 --port $PORT

Every request to the MCP endpoint (/mcp) must send `Authorization: Bearer <MCP_AUTH_TOKEN>`.
/health is open so the hosting platform can check the service is alive.
"""
import hmac
import os

from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse
from starlette.routing import Route

from mcp_server.server import mcp

MIN_TOKEN_LENGTH = 16


class BearerTokenMiddleware:
    """Rejects any HTTP request that does not carry the right bearer token."""

    def __init__(self, app, token: str):
        self.app = app
        self.token = token.encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == "/health":
            await self.app(scope, receive, send)
            return

        header = dict(scope["headers"]).get(b"authorization", b"").decode()
        supplied = header[7:] if header[:7].lower() == "bearer " else ""

        # compare_digest takes the same time however many characters match
        if not hmac.compare_digest(supplied.encode(), self.token):
            response = JSONResponse(
                {"error": "missing or invalid access token"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


async def _health(request):
    return JSONResponse({"status": "ok", "service": "hirepath-jobs-mcp"})


def build_app(token: str | None = None):
    token = token if token is not None else os.getenv("MCP_AUTH_TOKEN", "")
    if len(token) < MIN_TOKEN_LENGTH:
        # Refuse to start an unprotected public server.
        raise RuntimeError(
            f"MCP_AUTH_TOKEN must be set to a secret of at least {MIN_TOKEN_LENGTH} characters"
        )

    # Stateless + JSON responses: no in-memory sessions to lose when the host restarts
    # the service, and simpler for clients behind a proxy.
    mcp.settings.stateless_http = True
    mcp.settings.json_response = True
    # The library only accepts Host: localhost by default (a guard for unauthenticated local
    # servers). Behind a public hostname that would reject every request; the bearer token
    # is what protects this service.
    mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

    # The library creates the session manager once per server object and it can only
    # run once, so each app gets a fresh one (matters for tests; production builds one app).
    mcp._session_manager = None
    app = mcp.streamable_http_app()
    app.router.routes.append(Route("/health", _health))
    app.add_middleware(BearerTokenMiddleware, token=token)
    return app

