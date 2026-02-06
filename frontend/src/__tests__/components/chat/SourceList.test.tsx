import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import SourceList from '../../../components/chat/SourceList';

describe('SourceList', () => {
  const mockSources = [
    { id: '1', content: 'This is the first source content that should be displayed', score: 0.95 },
    { id: '2', content: 'This is the second source with a lot more content that exceeds the 100 character limit and should be truncated with ellipsis at the end of the preview', score: 0.85 },
    { id: '3', content: 'Short source', score: 0.75 },
  ];

  it('should not render when sources is empty', () => {
    const { container } = render(<SourceList sources={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('should not render when sources is undefined', () => {
    const { container } = render(<SourceList sources={undefined as any} />);
    expect(container.firstChild).toBeNull();
  });

  it('should render sources header', () => {
    render(<SourceList sources={mockSources} />);
    expect(screen.getByText('Sources:')).toBeInTheDocument();
  });

  it('should render all sources', () => {
    render(<SourceList sources={mockSources} />);
    expect(screen.getByText('[1]')).toBeInTheDocument();
    expect(screen.getByText('[2]')).toBeInTheDocument();
    expect(screen.getByText('[3]')).toBeInTheDocument();
  });

  it('should truncate long content with ellipsis', () => {
    render(<SourceList sources={mockSources} />);
    // The second source should be truncated
    expect(screen.getByText(/\.\.\.$/)).toBeInTheDocument();
  });

  it('should display source scores', () => {
    render(<SourceList sources={mockSources} />);
    expect(screen.getByText('(Score: 0.95)')).toBeInTheDocument();
    expect(screen.getByText('(Score: 0.85)')).toBeInTheDocument();
  });

  it('should not display score if not provided', () => {
    const sourcesWithoutScore = [{ id: '1', content: 'No score source' }];
    render(<SourceList sources={sourcesWithoutScore as any} />);
    expect(screen.queryByText(/Score:/)).not.toBeInTheDocument();
  });

  it('should render short content without ellipsis', () => {
    render(<SourceList sources={mockSources} />);
    expect(screen.getByText(/Short source/)).toBeInTheDocument();
    // This text should not have ellipsis
    const shortSourceText = screen.getByText(/Short source/).textContent;
    expect(shortSourceText).not.toContain('...');
  });
});
