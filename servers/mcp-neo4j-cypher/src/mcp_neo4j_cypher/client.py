from fastmcp import Client
from langchain.vectorstores.neo4j_vector import Neo4jVector
from langchain_community.embeddings import OllamaEmbeddings
import os
import anthropic
from dotenv import load_dotenv
import asyncio


client = Client("C:/Users/danie/Documents/internship/KG-road/mcp-neo4j/servers/mcp-neo4j-cypher/src/mcp_neo4j_cypher/run_mcp_server.py")

llm = anthropic.Anthropic(api_key = os.getenv("ANTHROPIC_API_KEY"))

embeddings = OllamaEmbeddings(
    model="nomic-embed-text:v1.5",
)




async def main():
    async with client:
        # tools = await client.list_tools()
        # print(f"Connected via Python Stdio, found tools: {tools}")
        # Execute via MCP server
        schema = await client.call_tool("get_neo4j_schema", {})
        print(schema)  # Inspect node labels, properties, and relationship types


asyncio.run(main())