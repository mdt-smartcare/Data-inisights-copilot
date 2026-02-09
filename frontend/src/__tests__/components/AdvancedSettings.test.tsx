import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import AdvancedSettings from '../../components/AdvancedSettings';

describe('AdvancedSettings', () => {
  const defaultSettings = {
    embedding: {
      model: 'BAAI/bge-m3',
      chunkSize: 800,
      chunkOverlap: 150,
    },
    retriever: {
      topKInitial: 50,
      topKFinal: 10,
      hybridWeights: [0.75, 0.25] as [number, number],
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
      expect(screen.getByText(/Fine-tune the RAG pipeline parameters/)).toBeInTheDocument();
    });

    it('should render embedding configuration section', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />);
      
      expect(screen.getByText('Embedding Strategy')).toBeInTheDocument();
      expect(screen.getByText('Model Name')).toBeInTheDocument();
      expect(screen.getByText('Chunk Size')).toBeInTheDocument();
      expect(screen.getByText('Overlap')).toBeInTheDocument();
    });

    it('should render retrieval configuration section', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />);
      
      expect(screen.getByText('Retrieval Parameters')).toBeInTheDocument();
      expect(screen.getByText('Top K (Initial)')).toBeInTheDocument();
      expect(screen.getByText('Top K (Final)')).toBeInTheDocument();
      expect(screen.getByText(/Hybrid Search Weights/)).toBeInTheDocument();
    });

    it('should display current settings values', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />);
      
      expect(screen.getByDisplayValue('BAAI/bge-m3')).toBeInTheDocument();
      expect(screen.getByDisplayValue('800')).toBeInTheDocument();
      expect(screen.getByDisplayValue('150')).toBeInTheDocument();
      expect(screen.getByDisplayValue('50')).toBeInTheDocument();
      expect(screen.getByDisplayValue('10')).toBeInTheDocument();
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
      
      // Find the model input by its current value
      const modelInput = screen.getByDisplayValue('BAAI/bge-m3');
      fireEvent.change(modelInput, { target: { value: 'sentence-transformers/all-MiniLM-L6-v2' } });
      
      expect(mockOnChange).toHaveBeenCalledWith(expect.objectContaining({
        embedding: expect.objectContaining({
          model: 'sentence-transformers/all-MiniLM-L6-v2',
        }),
      }));
    });

    it('should update chunk size when changed', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />);
      
      // Find chunk size by its current value (800)
      const chunkSizeInput = screen.getByDisplayValue('800');
      fireEvent.change(chunkSizeInput, { target: { value: '1000' } });
      
      expect(mockOnChange).toHaveBeenCalledWith(expect.objectContaining({
        embedding: expect.objectContaining({
          chunkSize: 1000,
        }),
      }));
    });

    it('should update chunk overlap when changed', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />);
      
      // Find overlap by its current value (150)
      const overlapInput = screen.getByDisplayValue('150');
      fireEvent.change(overlapInput, { target: { value: '200' } });
      
      expect(mockOnChange).toHaveBeenCalledWith(expect.objectContaining({
        embedding: expect.objectContaining({
          chunkOverlap: 200,
        }),
      }));
    });

    it('should update topKInitial when changed', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />);
      
      // Find topKInitial by its current value (50)
      const topKInitialInput = screen.getByDisplayValue('50');
      fireEvent.change(topKInitialInput, { target: { value: '100' } });
      
      expect(mockOnChange).toHaveBeenCalledWith(expect.objectContaining({
        retriever: expect.objectContaining({
          topKInitial: 100,
        }),
      }));
    });

    it('should update topKFinal when changed', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />);
      
      // Find topKFinal by its current value (10)
      const topKFinalInput = screen.getByDisplayValue('10');
      fireEvent.change(topKFinalInput, { target: { value: '15' } });
      
      expect(mockOnChange).toHaveBeenCalledWith(expect.objectContaining({
        retriever: expect.objectContaining({
          topKFinal: 15,
        }),
      }));
    });

    it('should update hybrid weights when slider is changed', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} />);
      
      const slider = screen.getByRole('slider');
      fireEvent.change(slider, { target: { value: '0.6' } });
      
      expect(mockOnChange).toHaveBeenCalledWith(expect.objectContaining({
        retriever: expect.objectContaining({
          hybridWeights: [0.6, 0.4],
        }),
      }));
    });
  });

  describe('Read Only Mode', () => {
    it('should disable all inputs when readOnly is true', () => {
      render(<AdvancedSettings settings={defaultSettings} onChange={mockOnChange} readOnly />);
      
      // Check that all inputs are disabled by checking their disabled attribute
      expect(screen.getByDisplayValue('BAAI/bge-m3')).toBeDisabled();
      expect(screen.getByDisplayValue('800')).toBeDisabled();
      expect(screen.getByDisplayValue('150')).toBeDisabled();
      expect(screen.getByDisplayValue('50')).toBeDisabled();
      expect(screen.getByDisplayValue('10')).toBeDisabled();
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
