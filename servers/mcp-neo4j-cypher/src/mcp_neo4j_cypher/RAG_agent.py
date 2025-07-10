from fastmcp import Client
import anthropic
import os
import json
from dotenv import load_dotenv
import asyncio

load_dotenv()

client = Client("C:/Users/danie/Documents/internship/KG-road/mcp-neo4j/servers/mcp-neo4j-cypher/src/mcp_neo4j_cypher/run_mcp_server.py")
llm_async = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPI_API_KEY"))
LLM_MODEL = "claude-3-5-haiku-latest"

CYPHER_GENERATION_PROMPT = """
You are a Neo4j Cypher expert helping to query a traffic incident management system. The knowledge graph contains:
- event_record nodes (traffic incidents)
- event_plan nodes (response plans)
- event_plan_command nodes (specific commands/actions)
- VMS nodes (variable message signs)
- Junction nodes (road junctions)
- Link nodes (road segments)

Key relationships:
- (event_record)-[HAS_PLAN]->(event_plan)
- (event_plan)-[HAS_COMMAND]->(event_plan_command)
- (event_plan_command)-[CONTROLS_VMS]->(VMS)
- (Link)-[TO_JUNCTION]->(Junction)
- (Junction)-[FROM_JUNCTION]->(Link)
- (event_record)-[START_AT]->(Link)
- (event_record)-[END_AT]->(Link)

When creating queries:
1. For incident details, start with MATCH (e:event_record)
2. For response plans, traverse HAS_PLAN relationship
3. For VMS messages, follow path through HAS_COMMAND and CONTROLS_VMS
4. For road network queries, use Link and Junction nodes
5. Use relationship patterns like (a)-[r:HAS_PLAN]->(b)
6. To find the VMS to use, check the link node for its length and find the VMS in the area
7. Ensure that the selcted VMS is on the same direction of the event ie if on the other direction it will be useless

Schema:
{schema}

Example Queries:
1. Find incident details:
    MATCH (e:event_record)
    WHERE e.id = $incident_id
    RETURN e.event_no, e.event_desc, e.road_name

2. Find related VMS:
    MATCH (e:event_record)-[:HAS_PLAN]->(p:event_plan)
     -[:HAS_COMMAND]->(c:event_plan_command)-[:CONTROLS_VMS]->(v:VMS)
    WHERE e.id = $incident_id
    RETURN v.EQT_NO, v.ROAD_NAME

Question: {question}

Return JSON with:
{{
  "operation": "read",
  "query": "CYPHER_QUERY",
  "params": {{PARAM_DICT}}
}}
"""

ITERATIVE_CYPHER_GENERATION_PROMPT = """
You are a Neo4j Cypher expert helping to query a traffic incident management system. Based on the previous context, generate a query to find additional relevant information.

Previous Context:
{extra_context}

Knowledge Graph Structure:
- event_record nodes (traffic incidents)
- event_plan nodes (response plans)
- event_plan_command nodes (specific commands/actions)
- VMS nodes (variable message signs)
- Junction nodes (road junctions)
- Link nodes (road segments)

Relationships:
- (event_record)-[HAS_PLAN]->(event_plan)
- (event_plan)-[HAS_COMMAND]->(event_plan_command)
- (event_plan_command)-[CONTROLS_VMS]->(VMS)
- (Link)-[TO_JUNCTION]->(Junction)
- (Junction)-[FROM_JUNCTION]->(Link)
- (event_record)-[START_AT]->(Link)
- (event_record)-[END_AT]->(Link)

Progressive Query Guidelines:
1. If incident found:
   - Look for similar incidents on same road
   - Find response plans for these incidents
   - Check nearby VMS signs

2. If response plan found:
   - Find similar successful response plans
   - Look for commonly used VMS messages
   - Check plan implementation status

3. If VMS found:
   - Find nearby VMS signs on same road
   - Check message history
   - Look for alternative routes

4. If road segment found:
   - Find connected segments
   - Check for incidents on connected segments
   - Look for alternative paths

Example Progressive Queries:
1. After finding an incident:
   MATCH (e:event_record)
   WHERE e.road_name = $road_name 
     AND e.event_type_id = $event_type_id
     AND e.id <> $original_id
   RETURN e.id, e.event_desc, e.start_time
   ORDER BY e.start_time DESC
   LIMIT 5

2. After finding a response plan:
   MATCH (p:event_plan)-[:HAS_COMMAND]->(c:event_plan_command)
   WHERE p.plan_type = $plan_type 
     AND p.is_implemented = 1
   RETURN p.id, c.msgDesc1, c.msgDesc2
   LIMIT 5

3. After finding VMS:
   MATCH (v:VMS)
   WHERE v.ROAD_NAME = $road_name
     AND v.EQT_NO <> $current_vms
   RETURN v.EQT_NO, v.ROAD_NAME, v.LATITUDE, v.LONGITUDE
   ORDER BY v.DIST_TO_UPNODE

Schema:
{schema}

Question: {question}

Return JSON with:
{{
  "operation": "read",
  "query": "CYPHER_QUERY",
  "params": {{PARAM_DICT}}
}}
"""

class CypherAgent:
    def __init__(self, client):
        self.client = client
        self.schema = None
    
    async def initialize(self):
        self.schema = await self.client.call_tool("get_neo4j_schema", {})
    

    async def generate_cypher(self, question: str, extra_context: str = ""):
        if extra_context:
            prompt = ITERATIVE_CYPHER_GENERATION_PROMPT.format(schema=self.schema, question=question, extra_context=extra_context)
        else:
            prompt = CYPHER_GENERATION_PROMPT.format(schema=self.schema, question=question)
        
        response = await llm_async.messages.create(
            model = LLM_MODEL,
            max_tokens = 1000,
            temperature = 0.1,
            system = "Return valid JSON only. No additional text.",
            messages = [{"role": "user", "content": prompt}]
        )
        
        try:
            return json.loads(response.content[0].text.strip())
        except json.JSONDecodeError:

            return {"operation": "read", "query": "MATCH (n) RETURN n LIMIT 0", "params": {}}
        

    async def execute_operation(self, operation_data):
        op_type = operation_data["operation"]
        query = operation_data["query"]
        params = operation_data.get("params", {})


        print("\n=== Neo4j Query Debug ===")
        print(f"Operation Type: {op_type}")
        print(f"Query:\n{query}")
        print(f"params: {params}")
        print("=" * 30)
        
        if op_type == "write":
            result = await self.client.call_tool("write_neo4j_cypher", {"query": query, "params": params})
        else:  
            result = await self.client.call_tool("read_neo4j_cypher", {"query": query, "params": params})


        print(f"\nResult type: {type(result)}")
        print("=" * 30)
        print(result)
        return result
        
def format_context(query_result) -> str:
    if not query_result or not isinstance(query_result, list) or not hasattr(query_result[0], "text"):
        return "No results found in database"

    try:
        if isinstance(query_result[0].text, str):
            data = json.loads(query_result[0].text)
        else:
            data = query_result[0].text
    except (json.JSONDecodeError, AttributeError, IndexError):
        return "Error processing Neo4j response"

    if not data:
        return "No results found in database"
    
    context_str = "Database Results:\n"
    for record in data:
        context_str += json.dumps(record, indent=2) + "\n\n"
    
    return context_str

async def generate_answer(question: str, context: str) -> str:
    prompt = f"""You are a data analyst. Answer the question based EXCLUSIVELY on the provided context to create a response plan in json format.

    Expected JSON format example:
    {{
        "vms_commands": [
            {{
                "eqt_no": "E11DMSG08N",
                "message_line_1": "INCIDENT AHEAD - SHEIKH ZAYED ROAD - FINANCIAL CENTER",
                "message_line_2": "USE CAUTION - EXPECT DELAYS",
                "display_duration": "60 minutes",
                "justification": "E11DMSG08N is the most relevant VMS based on proximity"
            }}
        ]
    }}
    
    Context:
    {context}
    
    Question: {question}
    
    Guidelines:
    - Return only valid JSON
    - Include vms_commands array with relevant messages
    - Provide justification for each VMS selection
    - If no data available, return empty vms_commands array

    Return the response plan as valid JSON:"""
    
    response = await llm_async.messages.create(
        model=LLM_MODEL,
        max_tokens=1000,
        temperature=0.3,
        system="Return valid JSON only. No additional text.",
        messages=[{"role": "user", "content": prompt}]
    )
    
    return response.content[0].text

async def rag(agent):
    try:
        question = input("\nEnter your question (type 'exit' to quit): ").strip()
        if question.lower() in ['exit', 'quit']:
            return False
        
        queried_aspects = set()
        accumulated_context = ""
        
        strategies = {
            "incident": {
                "aspect": "incident_details",
                "keywords": ["incident", "event", "accident", "emergency"]
            },
            "response": {
                "aspect": "response_plans",
                "keywords": ["response", "plan", "action", "command"]
            },
            "vms": {
                "aspect": "vms_details",
                "keywords": ["vms", "sign", "message", "display"]
            },
            "location": {
                "aspect": "road_network",
                "keywords": ["road", "junction", "link", "route", "path"]
            }
        }
        

        relevant_aspects = []
        for strategy in strategies.values():
            if any(keyword in question.lower() for keyword in strategy["keywords"]):
                relevant_aspects.append(strategy["aspect"])
        

        if not relevant_aspects:
            relevant_aspects = ["incident_details"]
        

        for iteration, aspect in enumerate(relevant_aspects, 1):
            if aspect in queried_aspects:
                continue
                
            print(f"\nIteration {iteration}: Querying {aspect}...")
            operation_data = await agent.generate_cypher(
                question, 
                extra_context=f"Previous findings:\n{accumulated_context}\nNext focus: {aspect}"
            )
            
            print(f"Generated Cypher:\n```\n{operation_data['query']}\n```")
            if operation_data["params"]:
                print(f"params: {operation_data['params']}")
            
            query_result = await agent.execute_operation(operation_data)
            new_context = format_context(query_result)
            
            if "No results found" not in new_context and new_context.strip():
                accumulated_context += f"\n=== {aspect.upper()} ===\n" + new_context
                queried_aspects.add(aspect)
                

                if aspect == "incident_details" and "road_name" in new_context:
                    relevant_aspects.extend(["response_plans", "vms_details"])
                elif aspect == "response_plans" and "plan_type" in new_context:
                    relevant_aspects.append("vms_details")
        
        if accumulated_context:
            print("\nFinal accumulated context:")
            print(accumulated_context)
            
            print("\nGenerating final answer based on the accumulated context...")
            answer = await generate_answer(question, accumulated_context)
            print(f"\nAnswer:\n{answer}\n")
        else:
            print("\nNo relevant information found in the database.")
            
        return True
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return True
    
async def main():
    async with client:
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

    class SessionAwareChatBot(RoadNetworkChatBot):
    def __init__(self):
        super().__init__()
        self.current_link = None
        self.current_road = None
    
    def set_link(self, link_id: str):
        self.current_link = link_id
        return f"✅ Working with link: {link_id}"
    
    def orchestrate_plan_generation(self, incident_text: str):
        """
        1. Get nearby events
        2. Get nearby VMS
        3. Combine them into context
        4. Pass to GenerateSmartResponsePlan
        """
        if not self.current_link:
            return "No link set. Please call set_link(link_id) first."
        
        link_id = self.current_link
        
        # Use the actual tool references (adjust indexes if your tool list changes order)
        find_events_tool = next(tool for tool in self.road_tools if tool.name == "FindEventRecord")
        find_vms_tool = next(tool for tool in self.road_tools if tool.name == "FindNearbyVMS")
        plan_tool = next(tool for tool in self.road_tools if tool.name == "GenerateSmartResponsePlan")
        
        # 1. Gather events
        events_data = find_events_tool.func(link_id)
        # 2. Gather VMS
        vms_data = find_vms_tool.func(link_id)
        
        # 3. Construct a single context string
        combined_context = f"""
            Incident: {incident_text}
            Events found: {events_data}
            VMS found: {vms_data}
        """
        # 4. Generate the plan
        return plan_tool.func(combined_context)

    def query(self, question: str):
        # Optional step to replace 'this link' with self.current_link
        if self.current_link and ("this link" in question.lower() or "that link" in question.lower()):
            question = question.replace("this link", self.current_link)
            question = question.replace("that link", self.current_link)
        
        # Call the normal query method
        return super().query(question)

session_chatbot = SessionAwareChatBot()