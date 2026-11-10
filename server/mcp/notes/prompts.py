from mcp.server import MCPServer


def register(mcp: MCPServer) -> None:
    @mcp.prompt()
    def summarize_note(text: str) -> str:
        """把一条笔记压缩成一句话"""
        return f"请用一句话总结下面的笔记：\n\n{text}"
