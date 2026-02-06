import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import DictionaryUploader from '../../components/DictionaryUploader';

describe('DictionaryUploader', () => {
  const mockOnUpload = vi.fn();

  beforeEach(() => {
    mockOnUpload.mockClear();
  });

  describe('Rendering', () => {
    it('should render the import button', () => {
      render(<DictionaryUploader onUpload={mockOnUpload} />);
      expect(screen.getByText('Import File')).toBeInTheDocument();
    });

    it('should render upload icon', () => {
      const { container } = render(<DictionaryUploader onUpload={mockOnUpload} />);
      expect(container.querySelector('svg')).toBeInTheDocument();
    });

    it('should have hidden file input', () => {
      const { container } = render(<DictionaryUploader onUpload={mockOnUpload} />);
      const input = container.querySelector('input[type="file"]');
      expect(input).toBeInTheDocument();
      expect(input).toHaveClass('hidden');
    });

    it('should accept correct file types', () => {
      const { container } = render(<DictionaryUploader onUpload={mockOnUpload} />);
      const input = container.querySelector('input[type="file"]');
      expect(input).toHaveAttribute('accept', '.csv,.json,.txt,.md');
    });
  });

  describe('Disabled State', () => {
    it('should disable button when disabled prop is true', () => {
      render(<DictionaryUploader onUpload={mockOnUpload} disabled />);
      const button = screen.getByText('Import File').closest('button');
      expect(button).toBeDisabled();
    });

    it('should apply disabled styles when disabled', () => {
      render(<DictionaryUploader onUpload={mockOnUpload} disabled />);
      const button = screen.getByText('Import File').closest('button');
      expect(button).toHaveClass('text-gray-400', 'cursor-not-allowed');
    });

    it('should have active styles when not disabled', () => {
      render(<DictionaryUploader onUpload={mockOnUpload} />);
      const button = screen.getByText('Import File').closest('button');
      expect(button).toHaveClass('text-blue-600');
    });
  });

  describe('File Upload - Text Files', () => {
    it('should handle plain text file upload', async () => {
      const { container } = render(<DictionaryUploader onUpload={mockOnUpload} />);
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;
      
      const file = new File(['Hello World'], 'test.txt', { type: 'text/plain' });
      
      Object.defineProperty(input, 'files', { value: [file] });
      fireEvent.change(input);
      
      await waitFor(() => {
        expect(mockOnUpload).toHaveBeenCalledWith('Hello World');
      });
    });

    it('should handle markdown file upload', async () => {
      const { container } = render(<DictionaryUploader onUpload={mockOnUpload} />);
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;
      
      const mdContent = '# Title\n\nSome content';
      const file = new File([mdContent], 'test.md', { type: 'text/markdown' });
      
      Object.defineProperty(input, 'files', { value: [file] });
      fireEvent.change(input);
      
      await waitFor(() => {
        expect(mockOnUpload).toHaveBeenCalledWith(mdContent);
      });
    });
  });

  describe('File Upload - JSON Files', () => {
    it('should handle valid JSON file and format it', async () => {
      const { container } = render(<DictionaryUploader onUpload={mockOnUpload} />);
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;
      
      const jsonContent = '{"key":"value","num":123}';
      const file = new File([jsonContent], 'test.json', { type: 'application/json' });
      
      Object.defineProperty(input, 'files', { value: [file] });
      fireEvent.change(input);
      
      await waitFor(() => {
        expect(mockOnUpload).toHaveBeenCalledWith(JSON.stringify({ key: 'value', num: 123 }, null, 2));
      });
    });

    it('should show error for invalid JSON file', async () => {
      const { container } = render(<DictionaryUploader onUpload={mockOnUpload} />);
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;
      
      const invalidJson = '{ invalid json }';
      const file = new File([invalidJson], 'test.json', { type: 'application/json' });
      
      Object.defineProperty(input, 'files', { value: [file] });
      fireEvent.change(input);
      
      await waitFor(() => {
        expect(screen.getByText(/Failed to parse file/)).toBeInTheDocument();
      });
      expect(mockOnUpload).not.toHaveBeenCalled();
    });
  });

  describe('File Upload - CSV Files', () => {
    it('should handle CSV file upload', async () => {
      const { container } = render(<DictionaryUploader onUpload={mockOnUpload} />);
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;
      
      const csvContent = 'name,value\nitem1,100\nitem2,200';
      const file = new File([csvContent], 'test.csv', { type: 'text/csv' });
      
      Object.defineProperty(input, 'files', { value: [file] });
      fireEvent.change(input);
      
      await waitFor(() => {
        expect(mockOnUpload).toHaveBeenCalledWith(csvContent);
      });
    });

    it('should handle CSV without commas (warn but still upload)', async () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      const { container } = render(<DictionaryUploader onUpload={mockOnUpload} />);
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;
      
      const badCsv = 'no commas here';
      const file = new File([badCsv], 'test.csv', { type: 'text/csv' });
      
      Object.defineProperty(input, 'files', { value: [file] });
      fireEvent.change(input);
      
      await waitFor(() => {
        expect(mockOnUpload).toHaveBeenCalledWith(badCsv);
      });
      expect(consoleSpy).toHaveBeenCalledWith("File doesn't look like standard CSV");
      consoleSpy.mockRestore();
    });
  });

  describe('Error Handling', () => {
    it('should display error alert when parsing fails', async () => {
      const { container } = render(<DictionaryUploader onUpload={mockOnUpload} />);
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;
      
      const file = new File(['{invalid}'], 'test.json', { type: 'application/json' });
      
      Object.defineProperty(input, 'files', { value: [file] });
      fireEvent.change(input);
      
      await waitFor(() => {
        expect(screen.getByText(/Failed to parse file/)).toBeInTheDocument();
      });
    });

    it('should allow dismissing the error', async () => {
      const { container } = render(<DictionaryUploader onUpload={mockOnUpload} />);
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;
      
      const file = new File(['{invalid}'], 'test.json', { type: 'application/json' });
      Object.defineProperty(input, 'files', { value: [file] });
      fireEvent.change(input);
      
      await waitFor(() => {
        expect(screen.getByText(/Failed to parse file/)).toBeInTheDocument();
      });
      
      // Click dismiss button (Alert component's dismiss)
      const dismissButton = screen.getByRole('button', { name: /dismiss|close/i });
      fireEvent.click(dismissButton);
      
      await waitFor(() => {
        expect(screen.queryByText(/Failed to parse file/)).not.toBeInTheDocument();
      });
    });
  });

  describe('No File Selected', () => {
    it('should not call onUpload when no file is selected', () => {
      const { container } = render(<DictionaryUploader onUpload={mockOnUpload} />);
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;
      
      Object.defineProperty(input, 'files', { value: [] });
      fireEvent.change(input);
      
      expect(mockOnUpload).not.toHaveBeenCalled();
    });
  });

  describe('Button Click', () => {
    it('should trigger file input click when button is clicked', () => {
      const { container } = render(<DictionaryUploader onUpload={mockOnUpload} />);
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;
      const clickSpy = vi.spyOn(input, 'click');
      
      const button = screen.getByText('Import File').closest('button')!;
      fireEvent.click(button);
      
      expect(clickSpy).toHaveBeenCalled();
    });

    it('should not trigger file input when disabled', () => {
      const { container } = render(<DictionaryUploader onUpload={mockOnUpload} disabled />);
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;
      const clickSpy = vi.spyOn(input, 'click');
      
      const button = screen.getByText('Import File').closest('button')!;
      fireEvent.click(button);
      
      expect(clickSpy).not.toHaveBeenCalled();
    });
  });
});
