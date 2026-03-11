# eval/reports/generate_report.py
import json
from pathlib import Path
from datetime import datetime

import sys
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from eval.config import logger

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RAG Evaluation Report</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1000px; margin: 0 auto; padding: 20px; }
        h1, h2, h3 { color: #2c3e50; }
        .header { border-bottom: 2px solid #eee; padding-bottom: 20px; margin-bottom: 30px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .card { background: #f8f9fa; border-radius: 8px; padding: 20px; border: 1px solid #e9ecef; }
        .metric-value { font-size: 2.5rem; font-weight: bold; color: #0066cc; margin: 10px 0; }
        .metric-label { font-size: 0.9rem; color: #6c757d; text-transform: uppercase; letter-spacing: 1px; }
        .pass { color: #28a745; }
        .fail { color: #dc3545; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 30px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #f1f3f5; font-weight: 600; }
        tr:hover { background-color: #f8f9fa; }
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Data Insights Copilot: RAG Evaluation Report</h1>
        <p>Generated on: <strong>{{ timestamp }}</strong></p>
    </div>

    <h2>1. RAGAS Metrics (Quality & Hallucination)</h2>
    <div class="grid">
        <div class="card">
            <div class="metric-label">Faithfulness (Anti-Hallucination)</div>
            <div class="metric-value {{ f_class }}">{{ faithfulness }}</div>
            <p>Score >= 0.75 is passing.</p>
        </div>
        <div class="card">
            <div class="metric-label">Answer Relevancy</div>
            <div class="metric-value {{ ar_class }}">{{ answer_relevancy }}</div>
            <p>Score >= 0.70 is passing.</p>
        </div>
        <div class="card">
            <div class="metric-label">Context Precision</div>
            <div class="metric-value {{ cp_class }}">{{ context_precision }}</div>
            <p>Score >= 0.65 is passing.</p>
        </div>
    </div>

    <h2>2. Retrieval Metrics (Vector Search)</h2>
    <div class="grid">
        <div class="card">
            <div class="metric-label">Hit Rate @ 5</div>
            <div class="metric-value {{ hr_class }}">{{ hit_rate }}</div>
            <p>Score >= 0.70 is passing.</p>
        </div>
        <div class="card">
            <div class="metric-label">Mean Reciprocal Rank (MRR)</div>
            <div class="metric-value {{ mrr_class }}">{{ mrr }}</div>
            <p>Score >= 0.60 is passing.</p>
        </div>
    </div>

    <h2>3. Intent Router Performance</h2>
    <div class="grid">
        <div class="card">
            <div class="metric-label">Routing Accuracy</div>
            <div class="metric-value {{ acc_class }}">{{ intent_accuracy }}</div>
            <p>Score >= 90% is passing.</p>
        </div>
        <div class="card">
            <div class="metric-label">Avg Latency</div>
            <div class="metric-value {{ lat_class }}">{{ intent_latency }} ms</div>
            <p>Must be < 200 ms.</p>
        </div>
    </div>

    <h2>4. SQL Generative Accuracy</h2>
    <div class="grid">
        <div class="card">
            <div class="metric-label">Execution Equivalence (DataFrames)</div>
            <div class="metric-value {{ sql_class }}">{{ sql_accuracy }}</div>
            <p>Score >= 80% is passing.</p>
        </div>
        <div class="card">
            <div class="metric-label">Queries Evaluated</div>
            <div class="metric-value">{{ sql_evaluated }}</div>
            <p>Passed: {{ sql_passed }} | Failed: {{ sql_failed }}</p>
        </div>
    </div>

    <h2>5. Clinical Safety Guardrails</h2>
    <div class="grid">
        <div class="card">
            <div class="metric-label">Average Safety Score (1-5)</div>
            <div class="metric-value">{{ safety_score }}</div>
            <p>Score 5 = Perfect clinical safety.</p>
        </div>
        <div class="card">
            <div class="metric-label">Compliance Pass Rate</div>
            <div class="metric-value {{ safety_class }}">{{ safety_pass }}</div>
            <p>Score >= 90% is passing. Violations: {{ safety_violations }}</p>
        </div>
    </div>

    <h2>6. End-to-End Pipeline Performance</h2>
    <div class="grid">
        <div class="card">
            <div class="metric-label">Avg ROUGE-L (Answer Consistency)</div>
            <div class="metric-value">{{ rouge_l }}</div>
        </div>
        <div class="card">
            <div class="metric-label">Avg E2E Latency</div>
            <div class="metric-value">{{ e2e_latency }} ms</div>
        </div>
    </div>
</body>
</html>
"""

def safe_load_json(filepath: Path) -> dict:
    if filepath.exists():
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load {filepath}: {e}")
    return {}

def format_score(val, is_percent=False):
    if val is None:
        return "N/A"
    if is_percent:
        return f"{val * 100:.1f}%"
    return f"{val:.2f}"

def get_class(val, threshold, higher_is_better=True):
    if val is None: return ""
    if higher_is_better:
        return "pass" if val >= threshold else "fail"
    else:
        return "pass" if val <= threshold else "fail"

def main():
    reports_dir = Path(__file__).parent
    
    # Load all results
    ragas_res = safe_load_json(reports_dir / "ragas_results.json")
    retrieval_res = safe_load_json(reports_dir / "retrieval_results.json")
    intent_res = safe_load_json(reports_dir / "intent_results.json")
    e2e_res = safe_load_json(reports_dir / "e2e_results.json")
    sql_res = safe_load_json(reports_dir / "sql_results.json")
    guardrail_res = safe_load_json(reports_dir / "guardrail_results.json")
    
    # Extract metrics safely
    f_score = ragas_res.get("faithfulness")
    ar_score = ragas_res.get("answer_relevancy")
    cp_score = ragas_res.get("context_precision")
    
    hr_score = retrieval_res.get("hit_rate@5")
    mrr_score = retrieval_res.get("mrr@5")
    
    intent_acc = intent_res.get("accuracy")
    intent_lat = intent_res.get("avg_latency_ms")
    
    rouge_l = e2e_res.get("avg_rouge_l")
    e2e_lat = e2e_res.get("avg_latency_ms")
    
    sql_acc = sql_res.get("sql_accuracy")
    sql_eval = sql_res.get("queries_evaluated")
    sql_pass = sql_res.get("equivalent_count")
    sql_fail = sql_res.get("failed_count")
    
    safety_score = guardrail_res.get("avg_safety_score")
    safety_pass = guardrail_res.get("pass_rate")
    safety_violations = guardrail_res.get("violations")
    
    # Render HTML
    html = HTML_TEMPLATE.replace("{{ timestamp }}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    html = html.replace("{{ faithfulness }}", format_score(f_score))
    html = html.replace("{{ f_class }}", get_class(f_score, 0.75))
    
    html = html.replace("{{ answer_relevancy }}", format_score(ar_score))
    html = html.replace("{{ ar_class }}", get_class(ar_score, 0.70))
    
    html = html.replace("{{ context_precision }}", format_score(cp_score))
    html = html.replace("{{ cp_class }}", get_class(cp_score, 0.65))
    
    html = html.replace("{{ hit_rate }}", format_score(hr_score, is_percent=True))
    html = html.replace("{{ hr_class }}", get_class(hr_score, 0.70))
    
    html = html.replace("{{ mrr }}", format_score(mrr_score))
    html = html.replace("{{ mrr_class }}", get_class(mrr_score, 0.60))
    
    html = html.replace("{{ intent_accuracy }}", format_score(intent_acc, is_percent=True))
    html = html.replace("{{ acc_class }}", get_class(intent_acc, 0.90))
    
    html = html.replace("{{ intent_latency }}", format_score(intent_lat))
    html = html.replace("{{ lat_class }}", get_class(intent_lat, 200, higher_is_better=False))
    
    html = html.replace("{{ sql_accuracy }}", format_score(sql_acc, is_percent=True))
    html = html.replace("{{ sql_class }}", get_class(sql_acc, 0.80))
    html = html.replace("{{ sql_evaluated }}", str(sql_eval) if sql_eval is not None else "N/A")
    html = html.replace("{{ sql_passed }}", str(sql_pass) if sql_pass is not None else "N/A")
    html = html.replace("{{ sql_failed }}", str(sql_fail) if sql_fail is not None else "N/A")
    
    html = html.replace("{{ safety_score }}", format_score(safety_score))
    html = html.replace("{{ safety_pass }}", format_score(safety_pass, is_percent=True))
    html = html.replace("{{ safety_class }}", get_class(safety_pass, 0.90))
    html = html.replace("{{ safety_violations }}", str(safety_violations) if safety_violations is not None else "N/A")
    
    html = html.replace("{{ rouge_l }}", format_score(rouge_l))
    html = html.replace("{{ e2e_latency }}", format_score(e2e_lat))
    
    output_html = reports_dir / "latest_report.html"
    with open(output_html, "w") as f:
        f.write(html)
        
    logger.info(f"Report generated successfully: {output_html}")
    
    # Also save a consolidated JSON
    consolidated = {
        "timestamp": datetime.now().isoformat(),
        "ragas": ragas_res,
        "retrieval": retrieval_res,
        "intent": intent_res,
        "sql": sql_res,
        "guardrails": guardrail_res,
        "e2e": e2e_res
    }
    with open(reports_dir / "latest_report.json", "w") as f:
        json.dump(consolidated, f, indent=2)

if __name__ == "__main__":
    main()
