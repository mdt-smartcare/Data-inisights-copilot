import { LineChart, Line, BarChart, Bar, PieChart, Pie, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell } from 'recharts';

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

const COLORS = ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#06b6d4', '#6366f1'];

export default function ChartRenderer({ chartData }: ChartRendererProps) {
  const { type, data: rawData, xKey, yKey, title, colors = COLORS } = chartData;

  if (!rawData) {
    return <div className="text-sm text-gray-500 italic">No data available for chart</div>;
  }

  // Transform data if it's in labels/values format (from backend)
  let data: any[];
  
  if (Array.isArray(rawData)) {
    // Already in array format
    data = rawData;
  } else if (rawData.labels && rawData.values) {
    // Transform from backend format: {labels: [...], values: [...]}
    // to Recharts format: [{name: ..., value: ...}, ...]
    data = rawData.labels.map((label: string, index: number) => {
      const value = rawData.values![index];
      // Convert string values to 0 (e.g., "Other" -> 0)
      const numericValue = typeof value === 'number' ? value : 0;
      return {
        name: label,
        value: numericValue
      };
    }).filter(item => item.value > 0); // Filter out zero/invalid values
  } else {
    return <div className="text-sm text-gray-500 italic">Invalid chart data format</div>;
  }

  if (data.length === 0) {
    return <div className="text-sm text-gray-500 italic">No valid data available for chart</div>;
  }

  const renderChart = () => {
    switch (type) {
      case 'line':
        return (
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={xKey || 'name'} tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              <Line type="monotone" dataKey={yKey || 'value'} stroke={colors[0]} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        );

      case 'bar':
        return (
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={xKey || 'name'} tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              <Bar dataKey={yKey || 'value'} fill={colors[0]} />
            </BarChart>
          </ResponsiveContainer>
        );

      case 'pie':
        return (
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={data}
                dataKey={yKey || 'value'}
                nameKey={xKey || 'name'}
                cx="50%"
                cy="50%"
                outerRadius={80}
                label={(entry) => entry.name}
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
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={xKey || 'name'} tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              <Area type="monotone" dataKey={yKey || 'value'} stroke={colors[0]} fill={colors[0]} fillOpacity={0.6} />
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
