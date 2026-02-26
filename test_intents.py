import asyncio
import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Force load the .env file
load_dotenv('.env')

from backend.services.agent_service import get_agent_service
from backend.sqliteDb.db import get_db_service

async def main():
    print("Initializing Database and AgentService...")
    db = get_db_service()
    # Attempt to initialize the default agent service
    service = get_agent_service()
    
    test_cases = [
        {
            "intent": "Intent A (SQL Only)",
            "query": "How many patients have systolic BP above 140?"
        },
        {
            "intent": "Intent B (Vector Only)",
            "query": "What symptoms of ketoacidosis appear in recent discharge summaries?"
        },
        {
            "intent": "Intent C (Hybrid)",
            "query": "Summarize the notes for all patients whose glucose was over 200 last week."
        }
    ]
    
    for i, tc in enumerate(test_cases):
        print(f"\n=======================================================")
        print(f"TEST {i+1}: {tc['intent']}")
        print(f"Query: {tc['query']}")
        print(f"=======================================================")
        
        try:
            # We use a unique session ID for each to avoid history contamination
            response = await service.process_query(
                query=tc["query"],
                user_id="test_user",
                session_id=f"test_session_{i}"
            )
            
            print("\nResponse:")
            print(response.get('answer', 'No answer generated.'))
            
            print("\nReasoning Steps (Tools Used):")
            steps = response.get('reasoning_steps', [])
            if not steps:
                print("  No reasoning steps recorded.")
            else:
                for step in steps:
                    # step is a pydantic model ReasoningStep
                    # It has 'tool' and 'input' attributes
                    tool_name = step.tool if hasattr(step, 'tool') else step.get('tool', 'Unknown Tool')
                    tool_input = step.input if hasattr(step, 'input') else step.get('input', '')
                    print(f"  - {tool_name}")
                    print(f"    Input: {tool_input[:200]}")
                    
        except Exception as e:
            print(f"\nERROR processing query: {e}")

if __name__ == "__main__":
    asyncio.run(main())
