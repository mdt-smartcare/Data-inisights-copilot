# Automating Vector DB Incremental Updates

To ensure your RAG Copilot is always querying the most recent data from your database (or updated files), you can trigger the **Update Vector DB** process automatically using a cron job, CI/CD pipeline, or task scheduler.

Because the update process tracks document checksums in a `document_index` SQL table, calling the update endpoint repeatedly is very cheap—it skips unmodified documents and only indexes the "delta" (new or modified rows).

## Method 1: Python Script (Recommended)

We've provided a helper script in `scripts/schedule_vector_db_update.py`.

### Prerequisites
1. You need a valid SuperAdmin `Bearer` token.
2. You need the `config_id` of the RAG configuration you want to update (found in the URL when editing a configuration).

### Usage
```bash
# Set your token as an environment variable
export COPILOT_ADMIN_TOKEN="your_super_admin_token_here"

# Run the script against config ID 5
python scripts/schedule_vector_db_update.py --config-id 5 --api-url "https://api.your-copilot-domain.com"
```

### Scheduling with Cron (Linux/macOS)
To run this automatically every night at 2:00 AM, add this to your server's crontab (`crontab -e`):

```bash
0 2 * * * export COPILOT_ADMIN_TOKEN="token"; /path/to/venv/bin/python /path/to/repo/scripts/schedule_vector_db_update.py --config-id 5 >> /var/log/vector_db_update.log 2>&1
```

## Method 2: Direct cURL Execution

You can bypass the Python script entirely by sending a direct `POST` request to the backend.

```bash
curl -X POST "https://api.your-copilot-domain.com/api/v1/embedding-jobs" \
     -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
           "config_id": 5, 
           "batch_size": 128, 
           "max_concurrent": 5, 
           "incremental": true 
         }'
```

This request immediately queues an asynchronous background task. 

## Verifying Success
1. **Logs**: Check your background API logs.
2. **Dashboard**: Log in to the Data Insights Copilot, open the Agent configuration wizard, and look at the **Manage Knowledge Base** card. The "Last Updated" timestamp and "Tracked Docs" metric will automatically reflect the most recent scheduled run.
