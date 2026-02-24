import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import AdvancedSettings from '../../components/AdvancedSettings';

describe('AdvancedSettings', () => {
  const defaultSettings = {
    embedding: {
      model: 'BAAI/bge-m3',
    },
    llm: {
      temperature: 0.0,
      maxTokens: 4096,
    },
    chunking: {
      parentChunkSize: 800,
      parentChunkOverlap: 150,
      childChunkSize: 200,
      childChunkOverlap: 50,
    },
    retriever: {
      topKInitial: 50,
      topKFinal: 10,
      hybridWeights: [0.75, 0.25] as [number, number],
      rerankEnabled: true,
      rerankerModel: 'BAAI/bge-reranker-base',
    },
  };

  const mockOnChange = vi.fn();

  beforeEach(() => {
    mockOnChange.mockClear();
  });

  describe('Rendering', () => {
    it('should render the component with title and description', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />);
      
      expect(screen.getByText('Advanced Configuration')).toBeInTheDocument();
    });

    it('should render embedding configuration section', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />);
      
      expect(screen.getByText('Embedding Strategy')).toBeInTheDocument();
    });

    it('should render retrieval configuration section', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />);
      
      expect(screen.getByText('Retrieval Parameters')).toBeInTheDocument();
    });

    it('should display current settings values', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />);
      
      expect(screen.getByDisplayValue('BAAI/bge-m3')).toBeInTheDocument();
    });

    it('should display hybrid weight values', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />);
      
      expect(screen.getByText('Vector: 0.75')).toBeInTheDocument();
      expect(screen.getByText('Keyword: 0.25')).toBeInTheDocument();
    });
  });

  describe('Editing', () => {
    it('should update model name when changed', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />);
      
      const modelInput = screen.getByDisplayValue('BAAI/bge-m3');
      fireEvent.change(modelInput, { target: { value: 'sentence-transformers/all-MiniLM-L6-v2' } });
      
      expect(mockOnChange).toHaveBeenCalled();
    });

    it('should update topKInitial when changed', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />);
      
      const topKInitialInput = screen.getByDisplayValue('50');
      fireEvent.change(topKInitialInput, { target: { value: '100' } });
      
      expect(mockOnChange).toHaveBeenCalled();
    });

    it('should update topKFinal when changed', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />);
      
      const topKFinalInput = screen.getByDisplayValue('10');
      fireEvent.change(topKFinalInput, { target: { value: '15' } });
      
      expect(mockOnChange).toHaveBeenCalled();
    });

    it('should update hybrid weights when slider is changed', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />);
      
      const slider = screen.getByRole('slider');
      fireEvent.change(slider, { target: { value: '0.6' } });
      
      expect(mockOnChange).toHaveBeenCalled();
    });
  });

  describe('Read Only Mode', () => {
    it('should disable all inputs when readOnly is true', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} readOnly />);
      
      expect(screen.getByDisplayValue('BAAI/bge-m3')).toBeDisabled();
      expect(screen.getByRole('slider')).toBeDisabled();
    });

    it('should not call onChange when readOnly and input is changed', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} readOnly />);
      
      const modelInput = screen.getByDisplayValue('BAAI/bge-m3');
      fireEvent.change(modelInput, { target: { value: 'new-model' } });
      
      expect(mockOnChange).not.toHaveBeenCalled();
    });
  });

  describe('Settings Sync', () => {
    it('should update local state when settings prop changes', () => {
      const { rerender } = render(
        <AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />
      );
      
      const newSettings = {
        ...defaultSettings,
        embedding: { ...defaultSettings.embedding, model: 'new-model-name' },
      };
      
      rerender(<AdvancedSettings settings={newSettings} onChange={mockOnChange} />);
      
      expect(screen.getByDisplayValue('new-model-name')).toBeInTheDocument();
    });
  });

  describe('Helper Text', () => {
    it('should display helper text for model field', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />);
      expect(screen.getByText(/HuggingFace model ID/)).toBeInTheDocument();
    });

    it('should display helper text for topK fields', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />);
      expect(screen.getByText('Candidates before reranking')).toBeInTheDocument();
      expect(screen.getByText('Results sent to LLM')).toBeInTheDocument();
    });
  });
});
