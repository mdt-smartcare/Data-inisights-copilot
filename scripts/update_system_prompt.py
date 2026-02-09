
import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.config_service import get_config_service
from backend.sqliteDb.db import get_db_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_system_prompt():
    """
    Updates the active system prompt in the database with the latest definition 
    from ConfigService (which now includes Radar, Treemap, and Scorecard instructions).
    """
    try:
        config_service = get_config_service()
        db_service = get_db_service()
        
        from backend.services.sql_service import get_sql_service
        sql_service = get_sql_service()
        
        logger.info("Fetching database schema info...")
        # Get table info (schema) from the SQL service
        schema_context = sql_service.db.get_table_info()
        
        logger.info("Generating draft prompt from ConfigService...")
        # Pass REAL schema context
        draft = config_service.generate_draft_prompt(schema_context)
        prompt_text = draft['draft_prompt']
        
        logger.info("Draft prompt generated. Length: %d chars", len(prompt_text))
        
        if "radar" not in prompt_text.lower():
            logger.error("❌ Draft prompt DOES NOT contain 'radar' instructions! Aborting.")
            return

        logger.info("Publishing new system prompt...")
        result = config_service.publish_system_prompt(
            prompt_text=prompt_text,
            user_id="script_update",
            reasoning="Automated update to include government visualization instructions (Scorecard, Radar, Treemap)"
        )
        
        logger.info("✅ Successfully published new system prompt!")
        logger.info("New Version: %s", result['version'])
        logger.info("Active: %s", result['is_active'])
        
    except Exception as e:
        logger.error(f"Failed to update system prompt: {e}")
        raise

if __name__ == "__main__":
    update_system_prompt()
