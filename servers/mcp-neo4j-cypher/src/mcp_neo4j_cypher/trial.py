from fastmcp import Client
import anthropic
import os
import json
from dotenv import load_dotenv
import asyncio

load_dotenv()

# Initialize clients
client = Client("C:/Users/danie/Documents/internship/KG-road/mcp-neo4j/servers/mcp-neo4j-cypher/src/mcp_neo4j_cypher/run_mcp_server.py")
llm_async = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPI_API_KEY"))
LLM_MODEL = "claude-3-5-haiku-latest"

CYPHER_GENERATION_PROMPT = """
You are a Neo4j Cypher expert. Convert the user's question into a valid Cypher query using ONLY the provided schema.
Follow these rules:
1. Use ONLY node labels, relationships, and properties from the schema
2. Never invent properties or relationships not in the schema
3. For missing information, use NULL values
4. Always use `WHERE` for filtering
5. Use `RETURN` to specify exactly what the question asks for
6. Format dates as strings: 'YYYY-MM-DD'
7. Escape special characters in strings
8. Use `DISTINCT` when appropriate
9. Use `LIMIT` for questions about top/bottom results
10. Use `COUNT` for "how many" questions
11. Prefer MERGE over CREATE for writes to avoid duplicates
12. Use parameters for dynamic values

Schema:
{schema}

Question: {question}

Return JSON with:
{{
  "operation": "read" or "write",
  "query": "CYPHER_QUERY",
  "parameters": {{PARAM_DICT}}
}}
"""
# class for cypher clients
class CypherAgent:
    def __init__(self, client):
        self.client = client
        self.schema = None
    
    async def initialize(self):
        """Load schema on startup"""
        self.schema = await self.client.call_tool("get_neo4j_schema", {})
    
    async def generate_cypher(self, question: str):
        """Generate Cypher query using LLM"""
        prompt = CYPHER_GENERATION_PROMPT.format(schema=self.schema, question=question)
        
        response = await llm_async.messages.create(
            model=LLM_MODEL,
            max_tokens=1000,
            temperature=0.1,
            system="Return valid JSON only. No additional text.",
            messages=[{"role": "user", "content": prompt}]
        )
        
        try:
            return json.loads(response.content[0].text.strip())
        except json.JSONDecodeError:
            # Fallback handling
            return {"operation": "read", "query": "MATCH (n) RETURN n LIMIT 0", "parameters": {}}
    
    async def execute_operation(self, operation_data):
        """Execute Cypher using appropriate MCP tool"""
        op_type = operation_data["operation"]
        query = operation_data["query"]
        params = operation_data.get("parameters", {})
        
        if op_type == "write":
            return await self.client.call_tool("write_neo4j_cypher", {"query": query, "parameters": params})
        else:  # Default to read
            return await self.client.call_tool("read_neo4j_cypher", {"query": query, "parameters": params})

def format_context(query_result) -> str:
    """Format Neo4j query results for LLM context"""
    if not query_result or not isinstance(query_result, list) or not hasattr(query_result[0], "text"):
        return "No results found in database"

    try:
        data = json.loads(query_result[0].text)
    except json.JSONDecodeError:
        return "Error decoding Neo4j response"

    if not data:
        return "No results found in database"
    
    context_str = "Database Results:\n"
    for record in data:
        context_str += json.dumps(record, indent=2) + "\n\n"
    
    return context_str

async def generate_answer(question: str, context: str) -> str:
    """Generate final answer using context"""
    prompt = f"""You are a data analyst. Answer the question based EXCLUSIVELY on the provided context.
    
    Context:
    {context}
    
    Question: {question}
    
    Guidelines:
    1. If context is missing relevant information, say "I don't know"
    2. Be concise but comprehensive
    3. For numerical results, include exact values
    4. For lists, show all items unless explicitly limited
    5. For comparison questions, highlight differences
    Answer:"""
    
    response = await llm_async.messages.create(
        model=LLM_MODEL,
        max_tokens=1000,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}]
    )
    
    return response.content[0].text

async def rag(agent):
    """Main RAG workflow"""
    try:
        question = input("\nEnter your question (type 'exit' to quit): ").strip()
        if question.lower() in ['exit', 'quit']:
            return False
        
        print(" Generating Cypher operation...")
        operation_data = await agent.generate_cypher(question)
        print(f"Operation Type: {operation_data['operation'].upper()}")
        print(f"Generated Cypher:\n```\n{operation_data['query']}\n```")
        if operation_data["parameters"]:
            print(f"Parameters: {operation_data['parameters']}")
        
        print(" Executing in Neo4j...")
        query_result = await agent.execute_operation(operation_data)
        
        print(" Formatting results...")
        context = format_context(query_result)
        
        print(" Generating answer...")
        answer = await generate_answer(question, context)
        print(f"\n Answer:\n{answer}\n")
        return True
        
    except Exception as e:
        print(f" Error: {str(e)}")
        return True

async def main():
    async with client:
        """Run continuous RAG session"""
        print("="*50)
        print("Neo4j RAG System Initialized")
        print("="*50)
    
        agent = CypherAgent(client)
        await agent.initialize()
        print(" Database schema loaded")
    
        while await rag(agent):
            continue

if __name__ == "__main__":
    asyncio.run(main())