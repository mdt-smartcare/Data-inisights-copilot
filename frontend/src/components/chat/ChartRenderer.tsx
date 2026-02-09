import { LineChart, Line, BarChart, Bar, PieChart, Pie, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell, LabelList } from 'recharts';

interface ChartData {
  type: 'line' | 'bar' | 'pie' | 'area';
  data: any[] | { labels?: string[]; values?: any[] };
  xKey?: string;
  yKey?: string;
  title?: string;
  colors?: string[];
}

interface ChartRendererProps {
  chartData: ChartData;
}

const COLORS = ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#06b6d4', '#6366f1', '#ef4444', '#84cc16'];

export default function ChartRenderer({ chartData }: ChartRendererProps) {
  const { type, data: rawData, xKey, yKey, title, colors = COLORS } = chartData;

  // Debug logging
  console.log('ChartRenderer received:', { type, title, rawData });

  if (!rawData) {
    console.warn('ChartRenderer: No rawData provided');
    return <div className="text-sm text-gray-500 italic">No data available for chart</div>;
  }

  // Transform data if it's in labels/values format (from backend)
  let data: any[] = [];
  let dataKeys: string[] = [];
  let isMultiSeries = false;

  if (Array.isArray(rawData)) {
    // Already in array format
    data = rawData;
    console.log('ChartRenderer: Using array format data', data);
  } else if (rawData.labels && rawData.values) {
    // Check if values are objects (multi-series/stacked) or primitives
    const firstValue = rawData.values[0];
    isMultiSeries = typeof firstValue === 'object' && firstValue !== null;

    if (isMultiSeries) {
      // Logic for Multi-Series (e.g., Stacked Bar)
      // Extract all unique keys from all value objects
      const allKeys = new Set<string>();
      rawData.values.forEach((v: any) => {
        if (v && typeof v === 'object') {
          Object.keys(v).forEach(k => allKeys.add(k));
        }
      });
      dataKeys = Array.from(allKeys);

      // Transform to Recharts format: [{name: 'Site A', 'Male': 10, 'Female': 5}, ...]
      data = rawData.labels.map((_, index: number) => {
        const valueObj = rawData.values![index] || {};
        return {
          name: rawData.labels![index], // Use index to match label
          ...valueObj
        };
      });
      console.log('ChartRenderer: Transformed multi-series data', { dataKeys, data });
    } else {
      // Logic for Single Series (original)
      dataKeys = [yKey || 'value']; // Default key
      data = rawData.labels.map((label: string, index: number) => {
        const value = rawData.values![index];
        const numericValue = typeof value === 'number' ? value : (parseFloat(value) || 0);
        return {
          name: label,
          value: numericValue
        };
      });
      console.log('ChartRenderer: Transformed single-series data', data);
    }
  } else {
    console.warn('ChartRenderer: Invalid data format', rawData);
    return <div className="text-sm text-gray-500 italic">Invalid chart data format</div>;
  }

  if (data.length === 0) {
    console.warn('ChartRenderer: No valid data after transformation');
    return <div className="text-sm text-gray-500 italic">No valid data available for chart</div>;
  }

  const renderChart = () => {
    switch (type) {
      case 'line':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={xKey || 'name'} tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              {isMultiSeries ? (
                dataKeys.map((key, index) => (
                  <Line
                    key={key}
                    type="monotone"
                    dataKey={key}
                    stroke={colors[index % colors.length]}
                    strokeWidth={2}
                  >
                    <LabelList dataKey={key} position="top" style={{ fontSize: '10px' }} />
                  </Line>
                ))
              ) : (
                <Line type="monotone" dataKey="value" stroke={colors[0]} strokeWidth={2}>
                  <LabelList dataKey="value" position="top" style={{ fontSize: '10px' }} />
                </Line>
              )}
            </LineChart>
          </ResponsiveContainer>
        );

      case 'bar':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={xKey || 'name'} tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip cursor={{ fill: 'transparent' }} />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              {isMultiSeries ? (
                dataKeys.map((key, index) => (
                  <Bar
                    key={key}
                    dataKey={key}
                    stackId="a" // Enable stacking
                    fill={colors[index % colors.length]}
                  >
                    {/* For stacked bars, position 'inside' keeps labels within the segments */}
                    <LabelList dataKey={key} position="inside" style={{ fill: '#fff', fontSize: '10px', textShadow: '0px 0px 2px rgba(0,0,0,0.5)' }} />
                  </Bar>
                ))
              ) : (
                <Bar dataKey="value" fill={colors[0]}>
                  <LabelList dataKey="value" position="top" style={{ fontSize: '12px' }} />
                </Bar>
              )}
            </BarChart>
          </ResponsiveContainer>
        );

      case 'pie':
        // Pie charts generally don't support stacked data well in this simple renderer
        // We'll just take the first series or default behavior
        return (
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={data}
                dataKey={isMultiSeries ? dataKeys[0] : "value"} // Fallback to first key if multi
                nameKey={xKey || 'name'}
                cx="50%"
                cy="50%"
                outerRadius={80}
                label={({ name, value }) => `${name}: ${value}`}
              >
                {data.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
            </PieChart>
          </ResponsiveContainer>
        );

      case 'area':
        return (
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={xKey || 'name'} tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              {isMultiSeries ? (
                dataKeys.map((key, index) => (
                  <Area
                    key={key}
                    type="monotone"
                    dataKey={key}
                    stackId="1"
                    stroke={colors[index % colors.length]}
                    fill={colors[index % colors.length]}
                    fillOpacity={0.6}
                  >
                    <LabelList dataKey={key} position="top" style={{ fontSize: '10px' }} />
                  </Area>
                ))
              ) : (
                <Area type="monotone" dataKey="value" stroke={colors[0]} fill={colors[0]} fillOpacity={0.6}>
                  <LabelList dataKey="value" position="top" style={{ fontSize: '10px' }} />
                </Area>
              )}
            </AreaChart>
          </ResponsiveContainer>
        );

      default:
        return <div className="text-sm text-gray-500">Unsupported chart type</div>;
    }
  };

  return (
    <div className="my-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
      {title && <h4 className="text-sm font-semibold mb-2 text-gray-700">{title}</h4>}
      {renderChart()}
    </div>
  );
}
