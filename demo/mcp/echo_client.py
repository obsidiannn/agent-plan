
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient


async def main():
    client = MultiServerMCPClient({
        "echo": {"command": "python", "args": ["demo/mcp/echo_server.py"],
                 "transport": "stdio"},
    })
    tools = await client.get_tools()          # 触发 server/discover
    print("发现工具:", [t.name for t in tools])
    print("调用结果:", await tools[0].ainvoke({"text": "hello mcp"}))

asyncio.run(main())
