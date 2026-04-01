import asyncio
import json
import httpx
from datetime import datetime

async def verify_qa_debug():
    url = "http://localhost:8000/api/v1/chat"
    payload = {
        "query": "How many patients are there?",
        "agent_id": "00000000-0000-0000-0000-000000000000", # Using dummy or valid agent ID
        "debug": True
    }
    
    print(f"🚀 Sending request with debug=True...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=30.0)
            
        print(f"✅ Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"📦 Response keys: {list(data.keys())}")
            
            if "qa_debug" in data and data["qa_debug"]:
                qa = data["qa_debug"]
                print("\n🐞 QA Debug Info Found:")
                print(f"  - SQL Query: {qa.get('sql_query')[:50]}..." if qa.get('sql_query') else "  - SQL Query: None")
                print(f"  - Reasoning Steps: {len(qa.get('reasoning_steps', []))}")
                print(f"  - Trace ID: {qa.get('trace_id')}")
                print(f"  - Trace URL: {qa.get('trace_url')}")
                print(f"  - Processing Time: {qa.get('processing_time_ms')}ms")
                
                # Check top level trace_id
                print(f"\n🔗 Top-level Trace ID: {data.get('trace_id')}")
                
                if data.get('trace_id') == qa.get('trace_id'):
                    print("✅ Trace IDs match!")
                else:
                    print("❌ Trace IDs MISMATCH!")
            else:
                print("❌ QA Debug Info MISSING or EMPTY!")
        else:
            print(f"❌ Error: {response.text}")
            
    except Exception as e:
        print(f"❌ Connection Error: {e}")

if __name__ == "__main__":
    asyncio.run(verify_qa_debug())
