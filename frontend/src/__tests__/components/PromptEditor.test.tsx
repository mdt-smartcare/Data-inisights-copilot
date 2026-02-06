import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import PromptEditor from '../../components/PromptEditor';

// Mock ReactMarkdown and remark-gfm
vi.mock('react-markdown', () => ({
  default: ({ children }: { children: string }) => <div data-testid="markdown-preview">{children}</div>,
}));

vi.mock('remark-gfm', () => ({
  default: () => {},
}));

// Mock clipboard API
Object.assign(navigator, {
  clipboard: {
    writeText: vi.fn().mockResolvedValue(undefined),
  },
});

describe('PromptEditor', () => {
  const mockOnChange = vi.fn();
  const sampleText = 'Hello, this is a test prompt.';

  beforeEach(() => {
    mockOnChange.mockClear();
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render Write and Preview tabs', () => {
      render(<PromptEditor value={sampleText} onChange={mockOnChange} />);
      
      expect(screen.getByRole('button', { name: 'Write' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Preview' })).toBeInTheDocument();
    });

    it('should show character count', () => {
      render(<PromptEditor value={sampleText} onChange={mockOnChange} />);
      expect(screen.getByText(`${sampleText.length} chars`)).toBeInTheDocument();
    });

    it('should render copy button', () => {
      render(<PromptEditor value={sampleText} onChange={mockOnChange} />);
      expect(screen.getByTitle('Copy to clipboard')).toBeInTheDocument();
    });

    it('should show textarea in Write mode by default', () => {
      render(<PromptEditor value={sampleText} onChange={mockOnChange} />);
      expect(screen.getByPlaceholderText('Enter your prompt here...')).toBeInTheDocument();
    });

    it('should display current value in textarea', () => {
      render(<PromptEditor value={sampleText} onChange={mockOnChange} />);
      expect(screen.getByDisplayValue(sampleText)).toBeInTheDocument();
    });
  });

  describe('Tab Switching', () => {
    it('should switch to Preview tab when clicked', () => {
      render(<PromptEditor value={sampleText} onChange={mockOnChange} />);
      
      fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
      
      expect(screen.getByTestId('markdown-preview')).toBeInTheDocument();
      expect(screen.queryByPlaceholderText('Enter your prompt here...')).not.toBeInTheDocument();
    });

    it('should switch back to Write tab when clicked', () => {
      render(<PromptEditor value={sampleText} onChange={mockOnChange} />);
      
      fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
      fireEvent.click(screen.getByRole('button', { name: 'Write' }));
      
      expect(screen.getByPlaceholderText('Enter your prompt here...')).toBeInTheDocument();
    });

    it('should highlight active tab', () => {
      render(<PromptEditor value={sampleText} onChange={mockOnChange} />);
      
      const writeTab = screen.getByRole('button', { name: 'Write' });
      expect(writeTab).toHaveClass('border-blue-500', 'text-blue-600');
      
      fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
      const previewTab = screen.getByRole('button', { name: 'Preview' });
      expect(previewTab).toHaveClass('border-blue-500', 'text-blue-600');
    });
  });

  describe('Text Editing', () => {
    it('should call onChange when text is typed', () => {
      render(<PromptEditor value="" onChange={mockOnChange} />);
      
      const textarea = screen.getByPlaceholderText('Enter your prompt here...');
      fireEvent.change(textarea, { target: { value: 'New content' } });
      
      expect(mockOnChange).toHaveBeenCalledWith('New content');
    });

    it('should update character count when value changes', () => {
      const { rerender } = render(<PromptEditor value="Short" onChange={mockOnChange} />);
      expect(screen.getByText('5 chars')).toBeInTheDocument();
      
      rerender(<PromptEditor value="Much longer text here" onChange={mockOnChange} />);
      expect(screen.getByText('21 chars')).toBeInTheDocument();
    });
  });

  describe('Toolbar', () => {
    it('should show toolbar in Write mode', () => {
      render(<PromptEditor value={sampleText} onChange={mockOnChange} />);
      
      expect(screen.getByTitle('Bold')).toBeInTheDocument();
      expect(screen.getByTitle('Italic')).toBeInTheDocument();
      expect(screen.getByTitle('Heading 3')).toBeInTheDocument();
      expect(screen.getByTitle('Bullet List')).toBeInTheDocument();
      expect(screen.getByTitle('Inline Code')).toBeInTheDocument();
    });

    it('should hide toolbar in Preview mode', () => {
      render(<PromptEditor value={sampleText} onChange={mockOnChange} />);
      
      fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
      
      expect(screen.queryByTitle('Bold')).not.toBeInTheDocument();
    });

    it('should hide toolbar in readOnly mode', () => {
      render(<PromptEditor value={sampleText} onChange={mockOnChange} readOnly />);
      
      expect(screen.queryByTitle('Bold')).not.toBeInTheDocument();
    });
  });

  describe('Formatting Buttons', () => {
    it('should insert bold formatting', () => {
      render(<PromptEditor value="" onChange={mockOnChange} />);
      
      fireEvent.click(screen.getByTitle('Bold'));
      
      expect(mockOnChange).toHaveBeenCalledWith('****');
    });

    it('should insert italic formatting', () => {
      render(<PromptEditor value="" onChange={mockOnChange} />);
      
      fireEvent.click(screen.getByTitle('Italic'));
      
      expect(mockOnChange).toHaveBeenCalledWith('**');
    });

    it('should insert heading formatting', () => {
      render(<PromptEditor value="" onChange={mockOnChange} />);
      
      fireEvent.click(screen.getByTitle('Heading 3'));
      
      expect(mockOnChange).toHaveBeenCalledWith('### ');
    });

    it('should insert bullet list formatting', () => {
      render(<PromptEditor value="" onChange={mockOnChange} />);
      
      fireEvent.click(screen.getByTitle('Bullet List'));
      
      expect(mockOnChange).toHaveBeenCalledWith('- ');
    });

    it('should insert inline code formatting', () => {
      render(<PromptEditor value="" onChange={mockOnChange} />);
      
      fireEvent.click(screen.getByTitle('Inline Code'));
      
      expect(mockOnChange).toHaveBeenCalledWith('``');
    });
  });

  describe('Copy to Clipboard', () => {
    it('should copy value to clipboard when copy button is clicked', async () => {
      render(<PromptEditor value={sampleText} onChange={mockOnChange} />);
      
      fireEvent.click(screen.getByTitle('Copy to clipboard'));
      
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(sampleText);
    });
  });

  describe('Read Only Mode', () => {
    it('should make textarea readonly when readOnly prop is true', () => {
      render(<PromptEditor value={sampleText} onChange={mockOnChange} readOnly />);
      
      const textarea = screen.getByDisplayValue(sampleText);
      expect(textarea).toHaveAttribute('readonly');
    });
  });

  describe('Preview Mode', () => {
    it('should render markdown content in preview', () => {
      render(<PromptEditor value="# Heading" onChange={mockOnChange} />);
      
      fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
      
      expect(screen.getByTestId('markdown-preview')).toHaveTextContent('# Heading');
    });

    it('should show placeholder text when content is empty in preview', () => {
      render(<PromptEditor value="" onChange={mockOnChange} />);
      
      fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
      
      expect(screen.getByTestId('markdown-preview')).toHaveTextContent('*No content to preview*');
    });
  });
});
