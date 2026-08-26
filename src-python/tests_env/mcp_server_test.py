from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ray-tracing-test")

@mcp.tool()
def hello_ray_tracing() -> str:
    """Returns a hello message to confirm the MCP server is reachable from Copilot."""
    return "ray-tracing tools are reachable"

if __name__ == "__main__":
    mcp.run()
