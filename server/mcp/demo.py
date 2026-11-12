from mcp.server import MCPServer

from . import chroma_rag, claw
from .auth import MCPPermissionMiddleware
from .notes import prompts, resources, tools


def create_mcp() -> MCPServer:
    """按领域组装 MCP server 的能力。

    新增领域时：建 server/mcp/<domain>/{tools,resources}.py，
    各自暴露 register(mcp)，再在这里追加一行注册即可。
    claw 领域对外暴露股吧检索/统计/采集工具与 claw:// 资源。
    chroma_rag 领域对外暴露 RAG 知识库检索/清单/导入工具与 rag:// 资源。
    能力鉴权统一挂在 middleware 上, 复用 sys_permission 的 RBAC。
    """
    server = MCPServer("agent-plan", middleware=[MCPPermissionMiddleware()])
    tools.register(server)
    resources.register(server)
    prompts.register(server)
    claw.register(server)
    chroma_rag.register(server)
    return server


mcp = create_mcp()
app = mcp.streamable_http_app()
