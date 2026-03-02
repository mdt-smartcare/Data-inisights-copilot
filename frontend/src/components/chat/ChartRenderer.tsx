import { useRef, useState } from 'react';
import { 
  LineChart, Line, BarChart, Bar, PieChart, Pie, AreaChart, Area, 
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, 
  Treemap, XAxis, YAxis, CartesianGrid, Tooltip, Legend, 
  ResponsiveContainer, Cell, LabelList, FunnelChart, Funnel
} from 'recharts';
import { domToPng } from 'modern-screenshot';

interface ChartData {
  type: 'line' | 'bar' | 'horizontal_bar' | 'pie' | 'area' | 'scorecard' | 'radar' | 'treemap' | 'gauge' | 'funnel' | 'bullet';
  data: any[] | { labels?: string[]; values?: any[] };
  xKey?: string;
  yKey?: string;
  title?: string;
  colors?: string[];
  // For Scorecard
  metrics?: { label: string; value: string | number; change?: string; status?: 'up' | 'down' | 'neutral' }[];
  // For Gauge
  value?: number;
  min?: number;
  max?: number;
  target?: number;
  thresholds?: { value: number; color: string; label?: string }[];
  // For Bullet
  actual?: number;
  comparative?: number;
  ranges?: number[];
}

interface ChartRendererProps {
  chartData: ChartData;
}

const COLORS = ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#06b6d4', '#6366f1', '#ef4444', '#84cc16'];

// Healthcare-specific color schemes
const GAUGE_COLORS = {
  danger: '#ef4444',
  warning: '#f59e0b', 
  success: '#10b981',
  neutral: '#6b7280'
};

const FUNNEL_COLORS = ['#3b82f6', '#6366f1', '#8b5cf6', '#a855f7', '#d946ef'];

export default function ChartRenderer({ chartData }: ChartRendererProps) {
  const { type, data: rawData, xKey, yKey, title, colors = COLORS, metrics } = chartData;
  const chartRef = useRef<HTMLDivElement>(null);
  const [isExporting, setIsExporting] = useState(false);

  // Debug logging
  console.log('ChartRenderer received:', { type, title, rawData, metrics });

  // ============================================
  // EXPORT FUNCTION - Capture rendered chart as PNG
  // ============================================
  const handleDownload = async () => {
    if (!chartRef.current || isExporting) return;
    
    setIsExporting(true);
    try {
      const dataUrl = await domToPng(chartRef.current, {
        scale: 2, // 2x resolution for crisp PPT images
        backgroundColor: '#ffffff',
      });
      
      // Download the PNG
      const link = document.createElement('a');
      link.download = `${(title || 'chart').replace(/[^a-zA-Z0-9]/g, '-')}-${new Date().toISOString().slice(0, 10)}.png`;
      link.href = dataUrl;
      link.click();
    } catch (err) {
      console.error('Failed to export chart:', err);
      alert('Failed to export. Try using screenshot:\n• Mac: Cmd+Shift+4\n• Windows: Win+Shift+S');
    } finally {
      setIsExporting(false);
    }
  };

  // Export toolbar component
  const ExportToolbar = () => (
    <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity z-20">
      <button
        onClick={handleDownload}
        disabled={isExporting}
        className="p-1.5 bg-white border border-gray-300 rounded shadow-sm hover:bg-gray-50 transition-colors disabled:opacity-50"
        title="Download as PNG (for PowerPoint)"
      >
        {isExporting ? (
          <svg className="w-4 h-4 text-gray-400 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
        ) : (
          <svg className="w-4 h-4 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
        )}
      </button>
    </div>
  );

  // ============================================
  // GAUGE CHART - For clinical thresholds & KPIs
  // ============================================
  if (type === 'gauge') {
    const { value = 0, min = 0, max = 100, target, thresholds } = chartData;
    const percentage = ((value - min) / (max - min)) * 100;
    
    // Determine color based on thresholds or default logic
    let gaugeColor = GAUGE_COLORS.neutral;
    if (thresholds && thresholds.length > 0) {
      for (const t of thresholds.sort((a, b) => b.value - a.value)) {
        if (value >= t.value) {
          gaugeColor = t.color;
          break;
        }
      }
    } else {
      // Default healthcare thresholds
      if (percentage >= 80) gaugeColor = GAUGE_COLORS.success;
      else if (percentage >= 60) gaugeColor = GAUGE_COLORS.warning;
      else gaugeColor = GAUGE_COLORS.danger;
    }

    return (
      <div className="relative group">
        <ExportToolbar />
        <div ref={chartRef} className="my-3 p-4 bg-white rounded-lg border border-gray-200 shadow-sm">
          {title && <h4 className="text-sm font-bold mb-4 text-gray-800 border-b pb-2">{title}</h4>}
          <div className="flex flex-col items-center">
            {/* SVG Gauge */}
            <svg viewBox="0 0 200 120" className="w-48 h-28">
              {/* Background arc */}
              <path
                d="M 20 100 A 80 80 0 0 1 180 100"
                fill="none"
                stroke="#e5e7eb"
                strokeWidth="12"
                strokeLinecap="round"
              />
              {/* Value arc */}
              <path
                d="M 20 100 A 80 80 0 0 1 180 100"
                fill="none"
                stroke={gaugeColor}
                strokeWidth="12"
                strokeLinecap="round"
                strokeDasharray={`${percentage * 2.51} 251`}
              />
              {/* Target marker */}
              {target !== undefined && (
                <line
                  x1={20 + ((target - min) / (max - min)) * 160}
                  y1="85"
                  x2={20 + ((target - min) / (max - min)) * 160}
                  y2="115"
                  stroke="#374151"
                  strokeWidth="2"
                  strokeDasharray="3 2"
                />
              )}
              {/* Value text */}
              <text x="100" y="85" textAnchor="middle" className="text-2xl font-bold" fill={gaugeColor}>
                {typeof value === 'number' ? value.toLocaleString() : value}
              </text>
              <text x="100" y="105" textAnchor="middle" className="text-xs" fill="#6b7280">
                {target ? `Target: ${target}` : `${min} - ${max}`}
              </text>
            </svg>
            {/* Legend for thresholds */}
            {thresholds && (
              <div className="flex gap-3 mt-2 text-xs">
                {thresholds.map((t, i) => (
                  <span key={i} className="flex items-center gap-1">
                    <span className="w-3 h-3 rounded-full" style={{ backgroundColor: t.color }}></span>
                    {t.label || `≥${t.value}`}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ============================================
  // FUNNEL CHART - For care cascades
  // ============================================
  if (type === 'funnel') {
    // Transform data for funnel
    let funnelData: any[] = [];
    if (Array.isArray(rawData)) {
      funnelData = rawData.map((item, index) => ({
        name: item.name || item.stage || `Stage ${index + 1}`,
        value: item.value || item.count || 0,
        fill: FUNNEL_COLORS[index % FUNNEL_COLORS.length]
      }));
    } else if (rawData?.labels && rawData?.values) {
      funnelData = rawData.labels.map((label: string, index: number) => ({
        name: label,
        value: rawData.values![index],
        fill: FUNNEL_COLORS[index % FUNNEL_COLORS.length]
      }));
    }

    // Calculate drop-off percentages
    const withDropoff = funnelData.map((item, index) => {
      if (index === 0) return { ...item, dropoff: null, percentage: 100 };
      const prevValue = funnelData[index - 1].value;
      const dropoff = prevValue > 0 ? ((prevValue - item.value) / prevValue * 100).toFixed(1) : 0;
      const percentage = funnelData[0].value > 0 ? (item.value / funnelData[0].value * 100).toFixed(1) : 0;
      return { ...item, dropoff, percentage };
    });

    return (
      <div className="relative group">
        <ExportToolbar />
        <div ref={chartRef} className="my-3 p-4 bg-white rounded-lg border border-gray-200 shadow-sm">
          {title && <h4 className="text-sm font-bold mb-4 text-gray-800 border-b pb-2">{title}</h4>}
          <div className="flex">
            <div className="flex-1">
              <ResponsiveContainer width="100%" height={300}>
                <FunnelChart>
                  <Tooltip formatter={(value: any) => [Number(value).toLocaleString()]} />
                  <Funnel dataKey="value" data={withDropoff} isAnimationActive>
                    {withDropoff.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.fill} />
                    ))}
                    <LabelList position="center" fill="#fff" stroke="none" dataKey="name" />
                  </Funnel>
                </FunnelChart>
              </ResponsiveContainer>
            </div>
            <div className="w-32 ml-4 text-xs space-y-2">
              {withDropoff.map((item, index) => (
                <div key={index} className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded" style={{ backgroundColor: item.fill }}></span>
                  <div>
                    <div className="font-medium">{item.value.toLocaleString()}</div>
                    {item.dropoff && <div className="text-red-500">↓ {item.dropoff}%</div>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ============================================
  // BULLET CHART - For performance vs target
  // ============================================
  if (type === 'bullet') {
    // Get target from multiple possible locations
    const dataTarget = (rawData as any)?.target;
    const defaultTarget = chartData.target ?? dataTarget ?? 0.8;
    const ranges = chartData.ranges ?? [30, 70, 100];
    
    // Transform data to bullet format
    let bulletData: { name: string; actual: number; target: number }[] = [];
    
    if (Array.isArray(rawData)) {
      // Array format: [{name: 'X', actual: 50, target: 80}, ...]
      bulletData = rawData.map(item => ({
        name: item.name || item.label || 'Item',
        actual: typeof item.actual === 'number' ? item.actual : parseFloat(item.actual) || 0,
        target: typeof item.target === 'number' ? item.target : defaultTarget
      }));
    } else if (rawData?.labels && rawData?.values) {
      // Labels/values format from backend
      // Get target from data object if available
      const targetFromData = rawData.target ?? defaultTarget;
      
      bulletData = rawData.labels.map((label: string, index: number) => {
        const value = rawData.values![index];
        
        // Skip if value is undefined (handles mismatched array lengths)
        if (value === undefined) return null;
        
        // Handle case where value is an object {actual, target}
        if (value && typeof value === 'object' && 'actual' in value) {
          let actualVal = typeof value.actual === 'number' ? value.actual : parseFloat(value.actual) || 0;
          let targetVal = typeof value.target === 'number' ? value.target : targetFromData;
          
          // If values are decimals (0-1), convert to percentage
          if (actualVal <= 1) actualVal = actualVal * 100;
          if (targetVal <= 1) targetVal = targetVal * 100;
          
          return {
            name: label,
            actual: actualVal,
            target: targetVal
          };
        }
        
        // Handle simple numeric value
        let numericValue = typeof value === 'number' ? value : parseFloat(value) || 0;
        let targetVal = typeof targetFromData === 'number' ? targetFromData : 0.8;
        
        // If values are decimals (0-1), convert to percentage
        if (numericValue <= 1) numericValue = numericValue * 100;
        if (targetVal <= 1) targetVal = targetVal * 100;
        
        return {
          name: label,
          actual: numericValue,
          target: targetVal
        };
      }).filter((item): item is { name: string; actual: number; target: number } => item !== null);
    } else if (chartData.actual !== undefined) {
      // Single bullet from chartData props
      let targetVal = defaultTarget;
      if (targetVal <= 1) targetVal = targetVal * 100;
      
      bulletData = [{ 
        name: title || 'Progress', 
        actual: chartData.actual, 
        target: targetVal
      }];
    }

    // If no data, show message
    if (bulletData.length === 0) {
      return <div className="text-sm text-gray-500 italic">No bullet chart data available</div>;
    }

    // Determine max value for scaling (safely handle empty arrays)
    const allValues = bulletData.flatMap(d => [d.actual, d.target]);
    const maxValue = Math.max(...allValues, ...ranges, 100);

    return (
      <div className="relative group">
        <ExportToolbar />
        <div ref={chartRef} className="my-3 p-4 bg-white rounded-lg border border-gray-200 shadow-sm">
          {title && <h4 className="text-sm font-bold mb-4 text-gray-800 border-b pb-2">{title}</h4>}
          <div className="space-y-4 max-h-96 overflow-y-auto">
            {bulletData.map((item, index) => {
              const scaledRanges = ranges.map(r => (r / maxValue) * 100);
              const scaledActual = (item.actual / maxValue) * 100;
              const scaledTarget = (item.target / maxValue) * 100;
              
              return (
                <div key={index} className="relative">
                  <div className="flex items-center mb-1">
                    <span className="text-xs font-medium text-gray-700 w-28 truncate" title={item.name}>
                      {item.name}
                    </span>
                    <span className="text-xs text-gray-500 ml-auto">
                      {item.actual.toFixed(1)}%
                    </span>
                  </div>
                  {/* Range backgrounds */}
                  <div className="relative h-6 bg-gray-100 rounded overflow-hidden">
                    {scaledRanges.map((range, i) => (
                      <div
                        key={i}
                        className="absolute h-full"
                        style={{
                          width: `${range}%`,
                          backgroundColor: i === 0 ? '#fee2e2' : i === 1 ? '#fef3c7' : '#d1fae5',
                          zIndex: scaledRanges.length - i
                        }}
                      />
                    ))}
                    {/* Actual bar */}
                    <div
                      className="absolute h-3 top-1.5 bg-gray-800 rounded"
                      style={{ width: `${Math.min(scaledActual, 100)}%`, zIndex: 10 }}
                    />
                    {/* Target marker */}
                    {item.target > 0 && (
                      <div
                        className="absolute w-0.5 h-full bg-red-500"
                        style={{ left: `${Math.min(scaledTarget, 100)}%`, zIndex: 11 }}
                      />
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          {/* Legend */}
          <div className="flex gap-4 text-xs text-gray-500 mt-4 pt-2 border-t">
            <span className="flex items-center gap-1"><span className="w-3 h-3 bg-red-100 rounded"></span>Poor (&lt;30%)</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 bg-yellow-100 rounded"></span>Fair (30-70%)</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 bg-green-100 rounded"></span>Good (&gt;70%)</span>
            <span className="flex items-center gap-1"><span className="w-3 h-1 bg-red-500"></span>Target</span>
          </div>
        </div>
      </div>
    );
  }

  // ============================================
  // HORIZONTAL BAR - For rankings
  // ============================================
  if (type === 'horizontal_bar') {
    // Transform data
    let barData: any[] = [];
    if (Array.isArray(rawData)) {
      barData = rawData;
    } else if (rawData?.labels && rawData?.values) {
      barData = rawData.labels.map((label: string, index: number) => ({
        name: label,
        value: rawData.values![index]
      }));
    }

    // Sort descending for ranking effect
    barData = [...barData].sort((a, b) => b.value - a.value);

    return (
      <div className="relative group">
        <ExportToolbar />
        <div ref={chartRef} className="my-3 p-4 bg-white rounded-lg border border-gray-200 shadow-sm">
          {title && <h4 className="text-sm font-bold mb-4 text-gray-800 border-b pb-2">{title}</h4>}
          <ResponsiveContainer width="100%" height={Math.max(200, barData.length * 35)}>
            <BarChart data={barData} layout="vertical" margin={{ top: 5, right: 30, left: 100, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={90} />
              <Tooltip />
              <Bar dataKey="value" fill={colors[0]} radius={[0, 4, 4, 0]}>
                <LabelList dataKey="value" position="right" style={{ fontSize: '11px' }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  // Handle Scorecard type specifically (doesn't use standard data transformation)
  if (type === 'scorecard') {
    // Transform standard data format (labels/values) to metrics if needed
    let displayMetrics = metrics;
    if (!displayMetrics && rawData && !Array.isArray(rawData)) {
      const typedRawData = rawData as any;
      if (typedRawData.value !== undefined || typedRawData.count !== undefined) {
        // Handle singular value (e.g. { value: 10 } or { count: 10 })
        displayMetrics = [{
          label: title || 'Total',
          value: typedRawData.value ?? typedRawData.count
        }];
      } else if (rawData.labels && rawData.values) {
        displayMetrics = rawData.labels.map((label: string, index: number) => ({
          label,
          value: rawData.values?.[index]
        }));
      }
    } else if (!displayMetrics && Array.isArray(rawData)) {
      displayMetrics = rawData;
    }

    return (
      <div className="relative group">
        <ExportToolbar />
        <div ref={chartRef} className="my-3 p-4 bg-white rounded-lg border border-gray-200 shadow-sm">
          {title && <h4 className="text-sm font-bold mb-4 text-gray-800 border-b pb-2">{title}</h4>}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
            {displayMetrics && displayMetrics.length > 0 ? (
              displayMetrics.map((metric: any, idx: number) => (
                <div key={idx} className="p-3 bg-gray-50 rounded-md border border-gray-100 flex flex-col items-center text-center">
                  <span className="text-xs text-gray-500 font-medium uppercase tracking-wide">{metric.label || metric.name || 'Metric'}</span>
                  <span className="text-xl font-bold text-gray-900 my-1">{metric.value}</span>
                  {metric.change && (
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${metric.status === 'up' ? 'bg-green-100 text-green-700' :
                      metric.status === 'down' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600'
                      } `}>
                      {metric.change}
                    </span>
                  )}
                </div>
              ))
            ) : (
              <div className="text-sm text-gray-500 italic col-span-3">No metrics data available</div>
            )}
          </div>
        </div>
      </div>
    );
  }

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
        // Pie charts use the transformed data format: [{name: "Label", value: Number}, ...]
        return (
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={data}
                dataKey="value" // Always use 'value' for single-series pie charts
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

      case 'radar':
        // Requires data in specific format, usually provided correctly by agent
        return (
          <ResponsiveContainer width="100%" height={300}>
            <RadarChart cx="50%" cy="50%" outerRadius="80%" data={data}>
              <PolarGrid />
              <PolarAngleAxis dataKey={xKey || 'name'} tick={{ fontSize: 11 }} />
              <PolarRadiusAxis />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              {isMultiSeries ? (
                dataKeys.map((key, index) => (
                  <Radar
                    key={key}
                    name={key}
                    dataKey={key}
                    stroke={colors[index % colors.length]}
                    fill={colors[index % colors.length]}
                    fillOpacity={0.3}
                  />
                ))
              ) : (
                <Radar name="Value" dataKey="value" stroke={colors[0]} fill={colors[0]} fillOpacity={0.5} />
              )}
            </RadarChart>
          </ResponsiveContainer>
        );

      case 'treemap':
        // Treemap needs nested data structure or flat list with weights
        return (
          <ResponsiveContainer width="100%" height={300}>
            <Treemap
              data={data}
              dataKey={yKey || 'value'}
              nameKey={xKey || 'name'}
              aspectRatio={4 / 3}
              stroke="#fff"
              fill={colors[0]}
              content={<CustomTreemapContent colors={colors} />}
            >
              <Tooltip />
            </Treemap>
          </ResponsiveContainer>
        );

      default:
        return <div className="text-sm text-gray-500">Unsupported chart type</div>;
    }
  };

  return (
    <div className="relative group">
      <ExportToolbar />
      <div ref={chartRef} className="my-3 p-3 bg-white rounded-lg border border-gray-200">
        {title && <h4 className="text-sm font-semibold mb-2 text-gray-700">{title}</h4>}
        {renderChart()}
      </div>
    </div>
  );
}

// Helper to colorize treemap cells
const CustomTreemapContent = (props: any) => {
  const { depth, x, y, width, height, index, colors, name, value } = props;
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        style={{
          fill: colors[index % colors.length],
          stroke: '#fff',
          strokeWidth: 2 / (depth + 1e-10),
          strokeOpacity: 1 / (depth + 1e-10),
        }}
      />
      {width > 50 && height > 30 && (
        <text x={x + width / 2} y={y + height / 2 + 7} textAnchor="middle" fill="#fff" fontSize={12}>
          {value}
        </text>
      )}
      {width > 50 && height > 50 && (
        <text x={x + width / 2} y={y + height / 2 - 7} textAnchor="middle" fill="#fff" fontSize={10} fontWeight="bold">
          {name}
        </text>
      )}
    </g>
  );
};
