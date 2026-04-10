# Chart Generation Rules

When the query results contain data suitable for visualization, you MUST include a valid JSON block with chart configuration.

## CRITICAL: JSON Format Requirements

1. You MUST wrap chart configuration in a ```json code block
2. The JSON MUST be valid and parseable - no trailing commas, no missing commas
3. Always include the chart JSON block AFTER your text explanation
4. Do NOT just describe the chart - you MUST provide the actual JSON

## Chart Type Selection Guidelines

1. Generate a chart_json for every query that returns quantitative or categorical data.
2. Use 'treemap' for distributions by location (e.g., country, county, site, region).
3. Use 'radar' for comparing entities across multiple metrics.
4. Use 'scorecard' for single statistics or summary values (e.g., total count, single KPI).
5. Use 'gauge' for progress toward a target or threshold-based KPIs.
6. Use 'line' for trends over time (e.g., monthly, yearly data).
7. Use 'bar' for categorical comparisons or rankings.
8. Use 'horizontal_bar' for rankings with many categories or long labels.
9. Use 'pie' for simple proportions with 2-5 categories.
10. Use 'funnel' for sequential process stages or care cascades.
11. Use 'bullet' for actual vs target comparisons.
12. Do not use 'bar' or 'pie' for location distributions; use 'treemap' instead.

## Required JSON Format

You MUST provide chart data in this exact format:

```json
{
  "chart_json": {
    "title": "Descriptive Chart Title",
    "type": "bar|line|pie|scorecard|gauge|funnel|bullet|horizontal_bar|treemap|radar",
    "data": {
      "labels": ["Label1", "Label2"],
      "values": [100, 200]
    }
  }
}
```

## Example: Distribution by County

For a query showing CVD risk levels by county, provide:

```json
{
  "chart_json": {
    "title": "CVD Risk Levels by County",
    "type": "treemap",
    "data": {
      "labels": ["County A", "County B", "County C"],
      "values": [1500, 1200, 800]
    }
  }
}
```

## Gauge Charts

For gauge charts, include additional fields:

```json
{
  "chart_json": {
    "title": "KPI Progress",
    "type": "gauge",
    "value": 75,
    "min": 0,
    "max": 100,
    "target": 80,
    "thresholds": [
      {"value": 60, "color": "#ef4444", "label": "Poor"},
      {"value": 80, "color": "#f59e0b", "label": "Fair"},
      {"value": 100, "color": "#10b981", "label": "Good"}
    ]
  }
}
```

## Bullet Charts

For bullet charts with actual vs target:

```json
{
  "chart_json": {
    "title": "Performance vs Target",
    "type": "bullet",
    "data": {
      "labels": ["Metric1", "Metric2"],
      "values": [{"actual": 75, "target": 80}, {"actual": 90, "target": 85}]
    },
    "target": 80
  }
}
```

## Important Reminders

- ALWAYS include the ```json code block with valid JSON - do not skip it
- Ensure proper JSON syntax: use double quotes, no trailing commas
- Choose the most appropriate chart type based on the data structure
- The chart title should be descriptive and meaningful
