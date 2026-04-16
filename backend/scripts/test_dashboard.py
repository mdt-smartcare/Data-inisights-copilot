import requests, json

url = "http://127.0.0.1:8000/api/v1/chat"
payload = {
    "query": "Give me an overview of Facility X",
    "session_id": "test-session",
    "agent_id": "8fd0f8fb-2eac-4f99-a6c7-cedf8ce893a0"
}
headers = {"Content-Type": "application/json"}

response = requests.post(url, data=json.dumps(payload), headers=headers)
if response.status_code == 200:
    data = response.json()
    chat_resp = data.get("data", {})
    dashboards = chat_resp.get("dashboards", [])
    print(f"Dashboards returned: {len(dashboards)}")
    for i, d in enumerate(dashboards):
        print(f"Chart {i+1}: type={d.get('type')}, title={d.get('title')}")
else:
    print(f"Error: {response.status_code}", response.text)
