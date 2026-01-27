
import sys
import os
from unittest.mock import MagicMock, patch

# Set path to allow imports
sys.path.append(os.getcwd())

from backend.sqliteDb.db import get_db_service
from backend.services.sql_service import SQLService

def verify_db():
    print("Verifying DB service...")
    db = get_db_service()
    metrics = db.get_active_metrics()
    print(f"Metrics in DB: {len(metrics)}")
    
    print("\nVerifying SQLService loading...")
    # Mock settings and SQLDatabase to avoid Postgres connection
    with patch("backend.services.sql_service.settings") as mock_settings:
        mock_settings.database_url = "sqlite:///:memory:"
        mock_settings.openai_api_key = "dummy"
        with patch("backend.services.sql_service.SQLDatabase") as mock_db:
            mock_db.from_uri.return_value.get_usable_table_names.return_value = []
            with patch("backend.services.sql_service.ChatOpenAI"):
                with patch("backend.services.sql_service.create_sql_agent"):
                    service = SQLService()
                    print(f"SQLService loaded {len(service.metrics)} metrics")
                    if len(service.metrics) > 0:
                        print(f"First metric: {service.metrics[0].name}")

if __name__ == "__main__":
    verify_db()
