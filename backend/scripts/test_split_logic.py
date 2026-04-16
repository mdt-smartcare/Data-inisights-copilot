import re

def test_split_logic(content):
    # This simulates the logic in ChatService._handle_dashboard_intent
    questions = [re.sub(r'^\d+[\)\.]\s*', '', q.strip()) for q in content.splitlines() if q.strip()]
    return questions

test_cases = [
    "1. Question one\n2. Question two\n3. Question three\n4. Question four",
    "Question one\nQuestion two\nQuestion three\nQuestion four",
    "1) Question one\n2) Question two\n3) Question three\n4) Question four",
    "\n\nQuestion one\n\nQuestion two\n\nQuestion three\n\nQuestion four\n\n",
]

for i, test in enumerate(test_cases):
    result = test_split_logic(test)
    print(f"Test case {i+1}:")
    print(f"Input: {test!r}")
    print(f"Output: {result}")
    assert len(result) == 4
    print("SUCCESS\n")
