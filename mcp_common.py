import json
import logging
from typing import Any, Mapping, cast

from dify_plugin.entities import I18nObject
from dify_plugin.entities.tool import (
    ToolDescription,
    ToolInvokeMessage,
    ToolParameter,
    ToolProviderType,
)
from dify_plugin.interfaces.agent import AgentToolIdentity, ToolEntity
from werkzeug import Request, Response

SERVER_NAME = "MCP Compatible Dify Tools"
SERVER_VERSION = "0.2.3"
SUPPORTED_PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")
DEFAULT_PROTOCOL_VERSION = "2025-03-26"

JSON_TYPE_BY_PARAMETER_TYPE = {
    ToolParameter.ToolParameterType.STRING: "string",
    ToolParameter.ToolParameterType.NUMBER: "number",
    ToolParameter.ToolParameterType.BOOLEAN: "boolean",
    ToolParameter.ToolParameterType.SELECT: "string",
}


def check_auth(r: Request, settings: Mapping) -> Response | None:
    expected = settings.get("auth_token")
    if not expected:
        return None

    provided = ""
    auth_header = r.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        provided = auth_header[7:].strip()
    if not provided:
        provided = (r.headers.get("X-Api-Key") or "").strip()
    if not provided:
        provided = (r.args.get("token") or "").strip()

    if provided == str(expected):
        return None

    return Response(
        json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": "Unauthorized"}}),
        status=401,
        content_type="application/json",
    )


def rpc_result(rpc_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


def rpc_error(rpc_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


def initialize_response(data: Mapping) -> dict:
    requested = (data.get("params") or {}).get("protocolVersion")
    version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else DEFAULT_PROTOCOL_VERSION
    return rpc_result(
        data.get("id"),
        {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        },
    )


def handle_rpc(session: Any, data: Mapping, settings: Mapping) -> dict:
    method = data.get("method")
    rpc_id = data.get("id")

    if method == "initialize":
        return initialize_response(data)
    if method == "ping":
        return rpc_result(rpc_id, {})
    if method == "tools/list":
        try:
            tools = init_tools(settings)
            return rpc_result(rpc_id, {"tools": init_mcp_tools(tools)})
        except Exception as e:
            logging.exception("tools/list failed")
            return rpc_error(rpc_id, -32000, str(e))
    if method == "tools/call":
        return tools_call_response(session, data, settings)
    return rpc_error(rpc_id, -32601, f"Unsupported method: {method}")


def tools_call_response(session: Any, data: Mapping, settings: Mapping) -> dict:
    rpc_id = data.get("id")
    try:
        tools = init_tools(settings)
        tool_map = build_tool_map(tools)

        params = data.get("params") or {}
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}

        tool = tool_map.get(tool_name)
        if tool is None:
            return rpc_error(rpc_id, -32602, f"Unknown tool: {tool_name}")

        result = invoke_tool(session, tool, arguments)
        return rpc_result(rpc_id, {"content": [{"type": "text", "text": result}], "isError": False})
    except Exception as e:
        logging.exception("tools/call failed")
        return rpc_result(
            rpc_id,
            {"content": [{"type": "text", "text": f"Tool invocation failed: {e}"}], "isError": True},
        )


def normalize_parameter_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(schema)
    name = normalized.get("name") or "param"

    label = normalized.get("label")
    if not isinstance(label, dict) or not label.get("en_US"):
        normalized["label"] = {"en_US": name}

    human_description = normalized.get("human_description")
    if not isinstance(human_description, dict) or not human_description.get("en_US"):
        normalized["human_description"] = {"en_US": name}

    if not normalized.get("type"):
        normalized["type"] = "string"

    if not normalized.get("form"):
        normalized["form"] = "llm"

    return normalized


def synthesize_parameter_schemas(
    parameter_values: Mapping[str, Any],
    settings_values: Mapping[str, Any],
) -> list[dict[str, Any]]:
    schemas = []

    for name, entry in parameter_values.items():
        if not name or name.startswith("__"):
            continue
        value = entry.get("value") if isinstance(entry, dict) else entry
        if value is not None:
            continue
        schemas.append({
            "name": name,
            "label": {"en_US": name},
            "human_description": {"en_US": name},
            "type": "string",
            "form": "llm",
            "required": False,
        })

    for name, entry in settings_values.items():
        if not name or name.startswith("__"):
            continue
        value = entry.get("value") if isinstance(entry, dict) else entry
        if value is not None:
            continue
        schemas.append({
            "name": name,
            "label": {"en_US": name},
            "human_description": {"en_US": name},
            "type": "string",
            "form": "form",
            "required": False,
        })

    return schemas


def parse_settings_overrides(raw: Any) -> dict[str, dict[str, Any]]:
    if not raw:
        return {}

    if isinstance(raw, Mapping):
        candidate = raw
    else:
        try:
            candidate = json.loads(raw)
        except Exception:
            logging.warning("settings_overrides is not valid JSON, ignored")
            return {}

    if not isinstance(candidate, Mapping):
        logging.warning("settings_overrides must be a JSON object, ignored")
        return {}

    result: dict[str, dict[str, Any]] = {}
    for tool_name, values in candidate.items():
        if isinstance(values, Mapping):
            result[str(tool_name)] = dict(values)
        else:
            logging.warning("settings_overrides entry for %s is not an object, ignored", tool_name)
    return result


def init_tools(settings: Mapping) -> list[ToolEntity]:
    result: list[ToolEntity] = []

    value = cast(list[dict[str, Any]], settings.get("tools") or [])
    value = [tool for tool in value if isinstance(tool, dict) and tool.get("enabled", False)]
    overrides = parse_settings_overrides(settings.get("settings_overrides"))

    for tool in value:
        tool_name = tool.get("tool_name")
        provider_name = tool.get("provider_name")
        if not tool_name or not provider_name:
            logging.warning("Skipping tool config without tool_name/provider_name: %s", tool)
            continue

        try:
            tool_type = tool.get("type") or "builtin"
            tool_label = tool.get("tool_label") or tool_name
            tool_description = tool.get("tool_description", None)
            extra_description = (tool.get("extra") or {}).get("description", None)
            schemas = tool.get("schemas") or []
            tool_settings = tool.get("settings") or {}
            parameter_values = tool.get("parameters") or {}

            identity = AgentToolIdentity(
                author="Dify",
                name=tool_name,
                label=I18nObject(en_US=tool_label),
                provider=provider_name,
            )

            llm_description = (
                extra_description
                if extra_description else tool_description
                if tool_description else tool_label
            )
            description = ToolDescription(
                human=I18nObject(en_US=llm_description),
                llm=llm_description,
            )

            provider_type = ToolProviderType.BUILT_IN
            if tool_type == "api":
                provider_type = ToolProviderType.API
            elif tool_type == "workflow":
                provider_type = ToolProviderType.WORKFLOW

            runtime_parameters = {}
            for parameter_name, parameter_value in tool_settings.items():
                if isinstance(parameter_value, dict):
                    runtime_parameters[parameter_name] = parameter_value.get("value")
                else:
                    runtime_parameters[parameter_name] = parameter_value

            if not schemas:
                schemas = synthesize_parameter_schemas(parameter_values, tool_settings)
                for parameter_name, parameter_value in parameter_values.items():
                    if isinstance(parameter_value, dict):
                        preset = parameter_value.get("value")
                    else:
                        preset = parameter_value
                    if preset is not None:
                        runtime_parameters[parameter_name] = preset

            runtime_parameters.update(overrides.get(tool_name) or {})

            parameters = []
            for schema in schemas:
                try:
                    parameters.append(ToolParameter(**normalize_parameter_schema(schema)))
                except Exception:
                    logging.exception("Skipping broken parameter schema of tool %s: %s", tool_name, schema)

            tool_entity = ToolEntity(
                identity=identity,
                parameters=parameters,
                description=description,
                provider_type=provider_type,
                runtime_parameters=runtime_parameters,
            )

            result.append(tool_entity)
        except Exception:
            logging.exception("Skipping tool %s: failed to load its config", tool_name)

    return result


def build_tool_map(tools: list[ToolEntity]) -> dict[str, ToolEntity]:
    tool_map: dict[str, ToolEntity] = {}
    for tool in tools:
        name = tool.identity.name
        if name in tool_map:
            name = f"{tool.identity.provider.split('/')[-1]}__{tool.identity.name}"
        suffix = 2
        base = name
        while name in tool_map:
            name = f"{base}_{suffix}"
            suffix += 1
        tool_map[name] = tool
    return tool_map


def init_mcp_tools(tools: list[ToolEntity] | None) -> list[dict]:
    mcp_tools = []
    for name, tool in build_tool_map(tools or []).items():
        try:
            mcp_tools.append(convert_tool_to_mcp_tool(name, tool))
        except Exception:
            logging.exception("Failed to convert Dify tool to MCP tool")
    return mcp_tools


def convert_tool_to_mcp_tool(name: str, tool: ToolEntity) -> dict:
    mcp_tool = {
        "name": name,
        "description": tool.description.llm if tool.description else "",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }

    for parameter in tool.parameters:
        if parameter.name.startswith("__"):
            continue
        if parameter.type in {
            ToolParameter.ToolParameterType.FILE,
            ToolParameter.ToolParameterType.FILES,
        }:
            continue

        is_llm_param = parameter.form == ToolParameter.ToolParameterForm.LLM
        if not is_llm_param and tool.runtime_parameters.get(parameter.name) is not None:
            continue

        description = parameter.llm_description or ""
        if not description and getattr(parameter, "human_description", None):
            description = parameter.human_description.en_US or ""

        property_schema = {
            "type": JSON_TYPE_BY_PARAMETER_TYPE.get(parameter.type, "string"),
            "description": description or parameter.name,
        }

        if parameter.type == ToolParameter.ToolParameterType.SELECT and parameter.options:
            property_schema["enum"] = [option.value for option in parameter.options]

        mcp_tool["inputSchema"]["properties"][parameter.name] = property_schema

        if parameter.required:
            mcp_tool["inputSchema"]["required"].append(parameter.name)

    return mcp_tool


def invoke_tool(session: Any, tool: ToolEntity, tool_call_args: Mapping) -> str:
    parameters = {
        key: value
        for key, value in {**tool.runtime_parameters, **tool_call_args}.items()
        if value is not None
    }

    tool_invoke_responses = session.tool.invoke(
        provider_type=ToolProviderType(tool.provider_type),
        provider=tool.identity.provider,
        tool_name=tool.identity.name,
        parameters=parameters,
    )

    result = ""
    for response in tool_invoke_responses:
        if response.type == ToolInvokeMessage.MessageType.TEXT:
            result += cast(ToolInvokeMessage.TextMessage, response.message).text
        elif response.type == ToolInvokeMessage.MessageType.LINK:
            result += (
                    f"result link: {cast(ToolInvokeMessage.TextMessage, response.message).text}."
                    + " please tell user to check it."
            )
        elif response.type in {
            ToolInvokeMessage.MessageType.IMAGE_LINK,
            ToolInvokeMessage.MessageType.IMAGE,
        }:
            result += f"Not support message type: {response.type}."
        elif response.type == ToolInvokeMessage.MessageType.JSON:
            text = json.dumps(
                cast(ToolInvokeMessage.JsonMessage, response.message).json_object,
                ensure_ascii=False,
            )
            result += f"tool response: {text}."
        else:
            result += f"tool response: {response.message!r}."

    return result
