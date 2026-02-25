import os
import sys
import logging
import argparse
import requests
from typing import Optional

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('vector_db_updater')

def trigger_update(api_url: str, token: str, config_id: int):
    """
    Triggers an incremental Vector DB update via the RAG Backend API.
    """
    endpoint = f"{api_url}/api/v1/embedding-jobs"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # We set incremental to True to perform a fast delta-sync
    payload = {
        "config_id": config_id,
        "batch_size": 50,
        "max_concurrent": 5,
        "incremental": True
    }
    
    logger.info(f"Triggering incremental update for config_id: {config_id} at {endpoint}")
    
    try:
        response = requests.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        
        data = response.json()
        job_id = data.get("job_id")
        logger.info(f"Successfully started job! Job ID: {job_id}")
        logger.info("Check the platform dashboard to monitor progress or history.")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to trigger update: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response Body: {e.response.text}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trigger an automated Vector DB Incremental Update")
    parser.add_argument("--config-id", type=int, required=True, help="The ID of the RAG configuration to update")
    parser.add_argument("--api-url", type=str, default=os.getenv("COPILOT_API_URL", "http://localhost:8000"), help="Base URL of the RAG backend")
    parser.add_argument("--token", type=str, default=os.getenv("COPILOT_ADMIN_TOKEN"), help="Admin Bearer token")
    
    args = parser.parse_args()
    
    if not args.token:
        logger.error("No auth token provided. Set COPILOT_ADMIN_TOKEN environment variable or pass --token.")
        sys.exit(1)
        
    trigger_update(args.api_url, args.token, args.config_id)
