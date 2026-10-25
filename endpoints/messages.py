import json
import uuid
from typing import Mapping

from dify_plugin import Endpoint
from werkzeug import Request, Response

from mcp_common import check_auth, handle_rpc


class MessageEndpoint(Endpoint):
    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        """
        Invokes the endpoint with the given request.
        """
        unauthorized = check_auth(r, settings)
        if unauthorized:
            return unauthorized

        session_id = r.args.get("session_id") or str(uuid.uuid4()).replace("-", "")
        data = r.get_json(silent=True) or {}
        method = data.get("method") or ""

        if isinstance(method, str) and method.startswith("notifications/"):
            return Response("", status=202, content_type="application/json")

        response = handle_rpc(self.session, data, settings)

        self.session.storage.set(session_id, json.dumps(response).encode())
        return Response("", status=202, content_type="application/json")
