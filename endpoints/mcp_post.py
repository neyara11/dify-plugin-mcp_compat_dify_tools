import json
import uuid
from typing import Mapping

from dify_plugin import Endpoint
from werkzeug import Request, Response

from mcp_common import check_auth, handle_rpc


class McpPostEndpoint(Endpoint):
    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        """
        The simplest MCP Streamable HTTP transport implementation.

        1. not validate the `Origin` header
        2. not valid session id
        3. not support Server-Sent Events (SSE)
        """
        unauthorized = check_auth(r, settings)
        if unauthorized:
            return unauthorized

        data = r.get_json(silent=True) or {}
        method = data.get("method") or ""

        if isinstance(method, str) and method.startswith("notifications/"):
            return Response("", status=202, content_type="application/json")

        response = handle_rpc(self.session, data, settings)

        headers = {}
        if method == "initialize":
            headers["mcp-session-id"] = str(uuid.uuid4()).replace("-", "")

        return Response(
            json.dumps(response),
            status=200,
            content_type="application/json",
            headers=headers,
        )
