import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import ConfigSummary from '../../components/ConfigSummary';

describe('ConfigSummary', () => {
  const defaultProps = {
    connectionId: 123,
    dataSourceType: 'database' as const,
    schema: {
      patients: ['id', 'name', 'dob'],
      encounters: ['id', 'patient_id', 'date'],
    },
    dataDictionary: 'Sample dictionary content',
    activePromptVersion: 2,
    totalPromptVersions: 5,
    lastUpdatedBy: 'admin',
    settings: {
      embedding: {
        model: 'BAAI/bge-m3',
        vectorDbName: 'test_db',
      },
      llm: {
        temperature: 0.0,
        maxTokens: 4096,
      },
    },
  };

  describe('Data Source Card', () => {
    it('should render the data source card', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText('Data Source')).toBeInTheDocument();
    });

    it('should show database type when dataSourceType is database', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText('SQL Database')).toBeInTheDocument();
    });

    it('should display the connection ID', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText(/ID: 123/)).toBeInTheDocument();
    });
  });

  describe('Intelligence Map Card', () => {
    it('should render the intelligence map card', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText('Intelligence Map')).toBeInTheDocument();
    });

    it('should show the correct entity (table) count', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText('2')).toBeInTheDocument();
      expect(screen.getByText('Entities')).toBeInTheDocument();
    });

    it('should show the correct attribute (column) count', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText('6')).toBeInTheDocument();
      expect(screen.getByText('Attributes')).toBeInTheDocument();
    });
  });

  describe('Logic Engine Card', () => {
    it('should render the logic engine card', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText('Logic Engine')).toBeInTheDocument();
    });

    it('should show active prompt version', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText('v2')).toBeInTheDocument();
    });

    it('should show temperature setting', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText('0.0')).toBeInTheDocument();
    });

    it('should show max tokens setting', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText('4096')).toBeInTheDocument();
    });
  });

  describe('Data Dictionary Card', () => {
    it('should render the context card', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText('Context & Dictionary')).toBeInTheDocument();
    });

    it('should show dictionary added status when content exists', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText('Data Dictionary Added')).toBeInTheDocument();
    });

    it('should show no dictionary status when empty', () => {
      render(<ConfigSummary {...defaultProps} dataDictionary="" />);
      expect(screen.getByText('No Dictionary Content')).toBeInTheDocument();
    });

    it('should show character count', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText('25 characters provided')).toBeInTheDocument();
    });
  });

  describe('Edge Cases', () => {
    it('should handle null connection ID', () => {
      render(<ConfigSummary {...defaultProps} connectionId={null} />);
      expect(screen.getByText('Data Source')).toBeInTheDocument();
    });

    it('should handle empty schema', () => {
      render(<ConfigSummary {...defaultProps} schema={{}} />);
      const zeros = screen.getAllByText('0');
      expect(zeros.length).toBeGreaterThanOrEqual(2);
    });

    it('should handle null activePromptVersion', () => {
      render(<ConfigSummary {...defaultProps} activePromptVersion={null} />);
      expect(screen.getByText('Logic Engine')).toBeInTheDocument();
    });

    it('should handle file data source type', () => {
      render(<ConfigSummary {...defaultProps} dataSourceType="file" fileInfo={{ name: 'test.pdf', type: 'pdf' }} />);
      expect(screen.getByText('Uploaded File')).toBeInTheDocument();
    });

    it('should show +N more when more than 5 tables', () => {
      const propsWithMoreTables = {
        ...defaultProps,
        schema: {
          table1: ['col1'],
          table2: ['col1'],
          table3: ['col1'],
          table4: ['col1'],
          table5: ['col1'],
          table6: ['col1'],
          table7: ['col1'],
        },
      };
      render(<ConfigSummary {...propsWithMoreTables} />);
      expect(screen.getByText('+2 more')).toBeInTheDocument();
    });
  });
});
