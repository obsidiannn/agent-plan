from mcp.server import MCPServer


def register(mcp: MCPServer) -> None:
    @mcp.tool()
    def add_note(text: str) -> str:
        """Save a note."""
        return f"Saved: {text}"
