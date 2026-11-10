from mcp.server.mcpserver import MCPServer

mcp = MCPServer("echo")


@mcp.tool()
def echo(text: str) -> str:
    """原样返回输入文本，用于验证发现与调用链路。"""
    return text


if __name__ == "__main__":
    mcp.run()   # stdio
