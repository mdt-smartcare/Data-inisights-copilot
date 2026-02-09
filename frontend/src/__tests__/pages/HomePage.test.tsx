import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import HomePage from '../../pages/HomePage';

const renderWithRouter = (component: React.ReactElement) => {
  return render(<MemoryRouter>{component}</MemoryRouter>);
};

describe('HomePage', () => {
  describe('Rendering', () => {
    it('should render the main heading', () => {
      renderWithRouter(<HomePage />);
      expect(screen.getByRole('heading', { name: /fhir rag assistant/i })).toBeInTheDocument();
    });

    it('should render the tagline', () => {
      renderWithRouter(<HomePage />);
      expect(screen.getByText(/ai-powered assistant for fhir healthcare data/i)).toBeInTheDocument();
    });

    it('should render the Start Chatting link', () => {
      renderWithRouter(<HomePage />);
      const chatLink = screen.getByRole('link', { name: /start chatting/i });
      expect(chatLink).toBeInTheDocument();
      expect(chatLink).toHaveAttribute('href', '/chat');
    });

    it('should render the Learn More link', () => {
      renderWithRouter(<HomePage />);
      const aboutLink = screen.getByRole('link', { name: /learn more/i });
      expect(aboutLink).toBeInTheDocument();
      expect(aboutLink).toHaveAttribute('href', '/about');
    });
  });

  describe('Feature Cards', () => {
    it('should render the AI-Powered feature card', () => {
      renderWithRouter(<HomePage />);
      expect(screen.getByRole('heading', { name: /ai-powered/i })).toBeInTheDocument();
      expect(screen.getByText(/advanced language models/i)).toBeInTheDocument();
    });

    it('should render the Fast Responses feature card', () => {
      renderWithRouter(<HomePage />);
      expect(screen.getByRole('heading', { name: /fast responses/i })).toBeInTheDocument();
      expect(screen.getByText(/optimized vector search/i)).toBeInTheDocument();
    });

    it('should render the Source Citations feature card', () => {
      renderWithRouter(<HomePage />);
      expect(screen.getByRole('heading', { name: /source citations/i })).toBeInTheDocument();
      expect(screen.getByText(/relevant source references/i)).toBeInTheDocument();
    });

    it('should render all three feature cards', () => {
      renderWithRouter(<HomePage />);
      const featureHeadings = screen.getAllByRole('heading', { level: 3 });
      expect(featureHeadings).toHaveLength(3);
    });
  });

  describe('Styling', () => {
    it('should have proper link styling classes', () => {
      renderWithRouter(<HomePage />);
      const chatLink = screen.getByRole('link', { name: /start chatting/i });
      expect(chatLink).toHaveClass('bg-blue-600');
    });
  });
});
