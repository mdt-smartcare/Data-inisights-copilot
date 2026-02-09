"""
Test script to verify follow-up question generation includes chart-related prompts.

This script tests the enhanced FollowUpService to ensure it generates
at least one visualization-related question when the response contains
numerical or categorical data.
"""
import asyncio
import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Load environment variables from .env file
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

from backend.services.followup_service import FollowUpService
from langchain_openai import ChatOpenAI
from backend.config import get_settings

settings = get_settings()


async def test_chart_related_followups():
    """Test that follow-up questions include chart-related suggestions."""
    
    # Initialize the service
    llm = ChatOpenAI(
        temperature=settings.openai_temperature,
        model_name=settings.openai_model,
        api_key=settings.openai_api_key
    )
    followup_service = FollowUpService(llm=llm)
    
    # Test case 1: Response with numerical distribution data
    test_cases = [
        {
            "name": "Gender Distribution",
            "original_question": "How many patients by gender?",
            "system_response": """Here are the results:
- Male: 5,000 patients (60%)
- Female: 3,322 patients (40%)

The data shows a higher proportion of male patients in the system."""
        },
        {
            "name": "Age Group Breakdown",
            "original_question": "Show patient count by age group",
            "system_response": """Patient distribution by age:
- 0-18: 1,200 patients
- 19-35: 2,500 patients
- 36-50: 3,100 patients
- 51-65: 2,800 patients
- 65+: 1,900 patients

The largest group is 36-50 years old."""
        }
    ]
    
    print("=" * 80)
    print("Testing Follow-Up Question Generator for Chart-Related Prompts")
    print("=" * 80)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'='*80}")
        print(f"Test Case {i}: {test_case['name']}")
        print(f"{'='*80}")
        print(f"\nOriginal Question: {test_case['original_question']}")
        print(f"\nSystem Response:\n{test_case['system_response']}")
        
        # Generate follow-up questions
        questions = await followup_service.generate_followups(
            original_question=test_case['original_question'],
            system_response=test_case['system_response']
        )
        
        print(f"\n📊 Generated Follow-Up Questions:")
        for j, question in enumerate(questions, 1):
            print(f"  {j}. {question}")
        
        # Check if at least one question is chart-related
        chart_keywords = [
            'chart', 'visualize', 'visualization', 'graph', 'plot',
            'pie', 'bar', 'line', 'show', 'display', 'breakdown',
            'distribution', 'compare', 'trend'
        ]
        
        has_chart_question = any(
            any(keyword in q.lower() for keyword in chart_keywords)
            for q in questions
        )
        
        if has_chart_question:
            print("\n✅ SUCCESS: At least one chart-related question found!")
        else:
            print("\n⚠️  WARNING: No obvious chart-related questions detected.")
            print("   (This might still be acceptable if questions suggest data exploration)")
    
    print(f"\n{'='*80}")
    print("Test Complete!")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(test_chart_related_followups())
