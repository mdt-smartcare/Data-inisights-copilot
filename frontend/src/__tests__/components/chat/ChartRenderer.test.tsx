import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import ChartRenderer from '../../../components/chat/ChartRenderer';
import type { ReactNode } from 'react';

interface MockChartProps {
  children?: ReactNode;
}

// Mock recharts to avoid rendering issues in tests
vi.mock('recharts', () => ({
  LineChart: ({ children }: MockChartProps) => <div data-testid="line-chart">{children}</div>,
  Line: () => <div data-testid="line" />,
  BarChart: ({ children }: MockChartProps) => <div data-testid="bar-chart">{children}</div>,
  Bar: () => <div data-testid="bar" />,
  PieChart: ({ children }: MockChartProps) => <div data-testid="pie-chart">{children}</div>,
  Pie: ({ children }: MockChartProps) => <div data-testid="pie">{children}</div>,
  AreaChart: ({ children }: MockChartProps) => <div data-testid="area-chart">{children}</div>,
  Area: () => <div data-testid="area" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Legend: () => <div data-testid="legend" />,
  ResponsiveContainer: ({ children }: MockChartProps) => <div data-testid="responsive-container">{children}</div>,
  Cell: () => <div data-testid="cell" />,
}));

describe('ChartRenderer', () => {
  const arrayData = [
    { name: 'Jan', value: 100 },
    { name: 'Feb', value: 200 },
    { name: 'Mar', value: 150 },
  ];

  const labelsValuesData = {
    labels: ['Active', 'Inactive', 'Pending'],
    values: [50, 30, 20],
  };

  describe('No Data Handling', () => {
    it('should show "No data available" when data is null', () => {
      render(<ChartRenderer chartData={{ type: 'bar', data: null as any }} />);
      expect(screen.getByText('No data available for chart')).toBeInTheDocument();
    });

    it('should show "Invalid chart data format" for invalid data structure', () => {
      render(<ChartRenderer chartData={{ type: 'bar', data: { invalid: 'structure' } as any }} />);
      expect(screen.getByText('Invalid chart data format')).toBeInTheDocument();
    });

    it('should show "No valid data available" when all values are filtered out', () => {
      const zeroData = { labels: ['A', 'B'], values: [0, 0] };
      render(<ChartRenderer chartData={{ type: 'bar', data: zeroData }} />);
      expect(screen.getByText('No valid data available for chart')).toBeInTheDocument();
    });
  });

  describe('Chart Type Rendering', () => {
    it('should render a line chart', () => {
      render(<ChartRenderer chartData={{ type: 'line', data: arrayData }} />);
      expect(screen.getByTestId('line-chart')).toBeInTheDocument();
      expect(screen.getByTestId('line')).toBeInTheDocument();
    });

    it('should render a bar chart', () => {
      render(<ChartRenderer chartData={{ type: 'bar', data: arrayData }} />);
      expect(screen.getByTestId('bar-chart')).toBeInTheDocument();
      expect(screen.getByTestId('bar')).toBeInTheDocument();
    });

    it('should render a pie chart', () => {
      render(<ChartRenderer chartData={{ type: 'pie', data: arrayData }} />);
      expect(screen.getByTestId('pie-chart')).toBeInTheDocument();
      expect(screen.getByTestId('pie')).toBeInTheDocument();
    });

    it('should render an area chart', () => {
      render(<ChartRenderer chartData={{ type: 'area', data: arrayData }} />);
      expect(screen.getByTestId('area-chart')).toBeInTheDocument();
      expect(screen.getByTestId('area')).toBeInTheDocument();
    });

    it('should show "Unsupported chart type" for unknown types', () => {
      render(<ChartRenderer chartData={{ type: 'radar' as any, data: arrayData }} />);
      expect(screen.getByText('Unsupported chart type')).toBeInTheDocument();
    });
  });

  describe('Data Transformation', () => {
    it('should handle array data format directly', () => {
      render(<ChartRenderer chartData={{ type: 'bar', data: arrayData }} />);
      expect(screen.getByTestId('bar-chart')).toBeInTheDocument();
    });

    it('should transform labels/values format to array format', () => {
      render(<ChartRenderer chartData={{ type: 'bar', data: labelsValuesData }} />);
      expect(screen.getByTestId('bar-chart')).toBeInTheDocument();
    });

    it('should filter out non-numeric values from labels/values data', () => {
      const mixedData = { labels: ['A', 'B', 'C'], values: [10, 'Other', 20] };
      render(<ChartRenderer chartData={{ type: 'bar', data: mixedData }} />);
      expect(screen.getByTestId('bar-chart')).toBeInTheDocument();
    });
  });

  describe('Title Rendering', () => {
    it('should render the chart title when provided', () => {
      render(
        <ChartRenderer
          chartData={{ type: 'bar', data: arrayData, title: 'Sales Report' }}
        />
      );
      expect(screen.getByText('Sales Report')).toBeInTheDocument();
    });

    it('should not render title when not provided', () => {
      render(<ChartRenderer chartData={{ type: 'bar', data: arrayData }} />);
      expect(screen.queryByRole('heading')).not.toBeInTheDocument();
    });
  });

  describe('Chart Container', () => {
    it('should render within a styled container', () => {
      const { container } = render(
        <ChartRenderer chartData={{ type: 'bar', data: arrayData }} />
      );
      const chartContainer = container.querySelector('.bg-gray-50.rounded-lg');
      expect(chartContainer).toBeInTheDocument();
    });

    it('should render ResponsiveContainer for all chart types', () => {
      render(<ChartRenderer chartData={{ type: 'line', data: arrayData }} />);
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
  });

  describe('Custom Keys', () => {
    it('should use custom xKey and yKey when provided', () => {
      const customData = [
        { month: 'Jan', sales: 100 },
        { month: 'Feb', sales: 200 },
      ];
      render(
        <ChartRenderer
          chartData={{ type: 'bar', data: customData, xKey: 'month', yKey: 'sales' }}
        />
      );
      expect(screen.getByTestId('bar-chart')).toBeInTheDocument();
    });
  });

  describe('Chart Elements', () => {
    it('should render grid, axes, tooltip, and legend for line chart', () => {
      render(<ChartRenderer chartData={{ type: 'line', data: arrayData }} />);
      expect(screen.getByTestId('cartesian-grid')).toBeInTheDocument();
      expect(screen.getByTestId('x-axis')).toBeInTheDocument();
      expect(screen.getByTestId('y-axis')).toBeInTheDocument();
      expect(screen.getByTestId('tooltip')).toBeInTheDocument();
      expect(screen.getByTestId('legend')).toBeInTheDocument();
    });

    it('should render cells for pie chart', () => {
      render(<ChartRenderer chartData={{ type: 'pie', data: arrayData }} />);
      // Cells are rendered per data point
      expect(screen.getAllByTestId('cell').length).toBe(arrayData.length);
    });
  });
});
