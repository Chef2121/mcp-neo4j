from fastmcp import Client
import anthropic
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()

client = Client("C:/Users/danie/Documents/internship/KG-road/mcp-neo4j/servers/mcp-neo4j-cypher/src/mcp_neo4j_cypher/run_mcp_server.py")
LLM_MODEL = "claude-3-5-haiku-latest"

# async def main():
#     async with client:
#         await client.ping()
#         print("Server is reachable")

# asyncio.run(main())

llm = anthropic.Anthropic(api_key = os.getenv("ANTHROPI_API_KEY"))

cypher_prompt = f""""""
params = " "

def generate_answer(question: str, context: str) -> str:
    """Generate answer using Anthropic Claude"""
    prompt = f"""You are a helpful assistant. Answer the question based on the provided context.
    Context:
    {context}

    Question: {question}

    Answer:"""

    message = llm.messages.create(
        model=LLM_MODEL,
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )

    return message.content[0].text


async def rag():
    question = input("Enter your question: ")
    print("---Analyzing Database---")
    try :
        async with client:
            graph_schema = await client.call_tool("get-neo4j-schema", {})
            
            cypher_llm = llm.messages.create(
                model = LLM_MODEL,
                max_tokens = 1000,
                messages = [{
                    "role" : "user",
                    "content" : prompt}]
            )
            read = await client.call_tool("read-neo4j-cypher", {"query" : []})
            
            write = await client.call_tool("write-neo4j-cypher", {"query" : []})
        
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        print("--- Client Interaction Finished ---")