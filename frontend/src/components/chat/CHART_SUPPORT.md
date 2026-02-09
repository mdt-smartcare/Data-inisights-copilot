# Chart Support in Assistant Messages

Assistant messages now support rendering various types of charts using the Recharts library.

## Supported Chart Types

1. **Line Chart** - For trends over time
2. **Bar Chart** - For comparing values
3. **Pie Chart** - For showing proportions
4. **Area Chart** - For showing cumulative data

## Usage

The backend can include chart data in two formats:

### Format 1: Code Block (Recommended)

\`\`\`chart
{
  "type": "bar",
  "title": "Patient Distribution by Age Group",
  "data": [
    { "name": "0-18", "value": 120 },
    { "name": "19-35", "value": 245 },
    { "name": "36-50", "value": 189 },
    { "name": "51-65", "value": 156 },
    { "name": "65+", "value": 98 }
  ],
  "xKey": "name",
  "yKey": "value"
}
\`\`\`

### Format 2: Tagged Format

```
[CHART]
{
  "type": "line",
  "title": "Blood Pressure Trend",
  "data": [
    { "date": "Week 1", "systolic": 120, "diastolic": 80 },
    { "date": "Week 2", "systolic": 118, "diastolic": 78 },
    { "date": "Week 3", "systolic": 122, "diastolic": 82 }
  ],
  "xKey": "date",
  "yKey": "systolic"
}
[/CHART]
```

## Chart Data Schema

```typescript
{
  type: 'line' | 'bar' | 'pie' | 'area';
  data: Array<object>;           // Chart data points
  xKey?: string;                 // X-axis key (default: 'name')
  yKey?: string;                 // Y-axis key (default: 'value')
  title?: string;                // Chart title
  colors?: string[];             // Custom colors (optional)
}
```

## Examples

### Bar Chart
```json
{
  "type": "bar",
  "title": "Resource Types in FHIR Bundle",
  "data": [
    { "resource": "Patient", "count": 45 },
    { "resource": "Observation", "count": 234 },
    { "resource": "Condition", "count": 78 },
    { "resource": "Medication", "count": 156 }
  ],
  "xKey": "resource",
  "yKey": "count"
}
```

### Line Chart
```json
{
  "type": "line",
  "title": "API Response Time (ms)",
  "data": [
    { "time": "1h", "ms": 120 },
    { "time": "2h", "ms": 135 },
    { "time": "3h", "ms": 110 },
    { "time": "4h", "ms": 125 }
  ],
  "xKey": "time",
  "yKey": "ms"
}
```

### Pie Chart
```json
{
  "type": "pie",
  "title": "Gender Distribution",
  "data": [
    { "name": "Male", "value": 520 },
    { "name": "Female", "value": 480 },
    { "name": "Other", "value": 45 }
  ]
}
```

### Area Chart
```json
{
  "type": "area",
  "title": "Cumulative Patient Registrations",
  "data": [
    { "month": "Jan", "value": 100 },
    { "month": "Feb", "value": 250 },
    { "month": "Mar", "value": 450 },
    { "month": "Apr", "value": 680 }
  ],
  "xKey": "month",
  "yKey": "value"
}
```

## Features

- **Responsive**: Charts automatically resize to fit container
- **Interactive**: Hover tooltips show data values
- **Customizable**: Support for custom colors
- **Accessible**: Legend and labels included
- **Compact**: Optimized sizing for chat interface

## Combining Charts with Text

Charts can be mixed with regular markdown content:

```
Here's an analysis of the patient data:

The distribution shows that most patients fall in the 19-35 age group.

```chart
{
  "type": "bar",
  "title": "Patient Ages",
  "data": [...]
}
```

As you can see from the chart above, there's a clear pattern...
```

The chart will be automatically extracted and rendered separately from the text.

## Default Colors

The default color palette includes:
- Blue (#3b82f6)
- Purple (#8b5cf6)
- Pink (#ec4899)
- Orange (#f59e0b)
- Green (#10b981)
- Cyan (#06b6d4)
- Indigo (#6366f1)

## Technical Details

- **Library**: Recharts (React charting library)
- **Rendering**: SVG-based, high performance
- **Size**: Charts are fixed at 250px height
- **Error Handling**: Graceful fallback for invalid data
