import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import PromptHistory from '../../components/PromptHistory';

const mockHistory = [
    { id: 1, version: 1, created_at: '2024-01-15T10:00:00Z', prompt_text: 'First version prompt with instructions for the AI assistant.', is_active: 0, created_by_username: 'admin' },
    { id: 2, version: 2, created_at: '2024-01-16T11:00:00Z', prompt_text: 'Updated prompt version 2 with enhanced instructions.', is_active: 1, created_by_username: 'editor' },
    { id: 3, version: 3, created_at: '2024-01-17T12:00:00Z', prompt_text: 'Latest version with improvements.', is_active: 0 },
];

describe('PromptHistory', () => {
    it('renders header and empty state when no history', () => {
        render(<PromptHistory history={[]} onSelect={() => {}} />);
        expect(screen.getByText('Version History')).toBeInTheDocument();
        expect(screen.getByText('No history available.')).toBeInTheDocument();
    });

    it('renders all versions with correct display elements', () => {
        render(<PromptHistory history={mockHistory} onSelect={() => {}} />);
        
        expect(screen.getByText(/v1/)).toBeInTheDocument();
        expect(screen.getByText(/v2/)).toBeInTheDocument();
        expect(screen.getByText(/v3/)).toBeInTheDocument();
        expect(screen.getByText(/\(Active\)/)).toBeInTheDocument();
        expect(screen.getByText('by admin')).toBeInTheDocument();
        expect(screen.getByText('by editor')).toBeInTheDocument();
        expect(screen.getAllByRole('listitem')).toHaveLength(3);
    });

    it('calls onSelect with correct data when clicking versions', () => {
        const onSelect = vi.fn();
        render(<PromptHistory history={mockHistory} onSelect={onSelect} />);
        
        fireEvent.click(screen.getByText(/v1/).closest('li')!);
        expect(onSelect).toHaveBeenCalledWith(mockHistory[0]);
        
        fireEvent.click(screen.getByText(/v2/).closest('li')!);
        expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 2, version: 2, is_active: 1 }));
    });

    it('highlights selected version and applies correct styling', () => {
        render(<PromptHistory history={mockHistory} onSelect={() => {}} currentVersionId={2} />);
        
        const selectedItem = screen.getByText(/v2/).closest('li');
        const nonSelectedItem = screen.getByText(/v1/).closest('li');
        
        expect(selectedItem).toHaveClass('bg-blue-50', 'border-blue-500');
        expect(nonSelectedItem).toHaveClass('border-transparent');
        
        // Check active version styling
        expect(screen.getByText(/v2 \(Active\)/)).toHaveClass('text-green-600');
        expect(screen.getByText(/v1/)).toHaveClass('text-gray-700');
    });

    it('handles edge cases: single item, null/undefined currentVersionId', () => {
        // Single item
        const { rerender } = render(<PromptHistory history={[mockHistory[0]]} onSelect={() => {}} />);
        expect(screen.getByText(/v1/)).toBeInTheDocument();
        expect(screen.queryByText(/v2/)).not.toBeInTheDocument();
        
        // Null currentVersionId
        rerender(<PromptHistory history={mockHistory} onSelect={() => {}} currentVersionId={null} />);
        screen.getAllByRole('listitem').forEach(item => expect(item).toHaveClass('border-transparent'));
        
        // Undefined currentVersionId
        rerender(<PromptHistory history={mockHistory} onSelect={() => {}} />);
        expect(screen.getByText('Version History')).toBeInTheDocument();
    });
});
