import json

from mcp.server import MCPServer


def register(mcp: MCPServer) -> None:
    @mcp.resource("notes://server/info")
    def server_info() -> str:
        """当前 MCP server 的基本信息"""
        return json.dumps({"name": mcp.name, "version": mcp.version}, ensure_ascii=False)
