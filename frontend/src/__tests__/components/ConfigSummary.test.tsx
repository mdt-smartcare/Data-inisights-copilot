import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import ConfigSummary from '../../components/ConfigSummary';

describe('ConfigSummary', () => {
  const defaultProps = {
    connectionId: 123,
    schema: {
      patients: ['id', 'name', 'dob'],
      encounters: ['id', 'patient_id', 'date'],
    },
    dataDictionary: 'Sample dictionary content',
    activePromptVersion: 2,
    totalPromptVersions: 5,
    lastUpdatedBy: 'admin',
  };

  describe('Database Connection Card', () => {
    it('should render the database connection card', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText('Database Connection')).toBeInTheDocument();
    });

    it('should show connected status', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText('Connected')).toBeInTheDocument();
    });

    it('should display the connection ID', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText('123')).toBeInTheDocument();
    });
  });

  describe('Schema Summary Card', () => {
    it('should render the schema summary card', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText('Data Schema')).toBeInTheDocument();
    });

    it('should show the correct table count', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText('2')).toBeInTheDocument();
      expect(screen.getByText('Tables Selected')).toBeInTheDocument();
    });

    it('should show the correct column count', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText('6')).toBeInTheDocument();
      expect(screen.getByText('Columns Included')).toBeInTheDocument();
    });

    it('should display table names', () => {
      render(<ConfigSummary {...defaultProps} />);
      expect(screen.getByText('patients')).toBeInTheDocument();
      expect(screen.getByText('encounters')).toBeInTheDocument();
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
      expect(screen.getByText('Database Connection')).toBeInTheDocument();
    });

    it('should handle empty schema', () => {
      render(<ConfigSummary {...defaultProps} schema={{}} />);
      const zeros = screen.getAllByText('0');
      expect(zeros.length).toBeGreaterThanOrEqual(2);
    });

    it('should handle null activePromptVersion', () => {
      render(<ConfigSummary {...defaultProps} activePromptVersion={null} />);
      expect(screen.getByText('System Prompt')).toBeInTheDocument();
    });
  });
});
