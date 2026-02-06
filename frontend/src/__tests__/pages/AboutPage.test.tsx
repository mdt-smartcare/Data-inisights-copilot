import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import AboutPage from '../../pages/AboutPage';

describe('AboutPage', () => {
  it('should render the page title', () => {
    render(<AboutPage />);
    expect(screen.getByRole('heading', { name: /about fhir rag/i })).toBeInTheDocument();
  });

  it('should render the What is FHIR RAG section', () => {
    render(<AboutPage />);
    expect(screen.getByRole('heading', { name: /what is fhir rag/i })).toBeInTheDocument();
    expect(screen.getByText(/ai-powered assistant/i)).toBeInTheDocument();
  });

  it('should render the How It Works section', () => {
    render(<AboutPage />);
    expect(screen.getByRole('heading', { name: /how it works/i })).toBeInTheDocument();
    expect(screen.getByText(/ask questions in natural language/i)).toBeInTheDocument();
    expect(screen.getByText(/vector embeddings/i)).toBeInTheDocument();
  });

  it('should render the Technology Stack section', () => {
    render(<AboutPage />);
    expect(screen.getByRole('heading', { name: /technology stack/i })).toBeInTheDocument();
    expect(screen.getByText(/React, TypeScript, Tailwind CSS/i)).toBeInTheDocument();
    expect(screen.getByText(/Python, FastAPI/i)).toBeInTheDocument();
  });

  it('should render the Use Cases section', () => {
    render(<AboutPage />);
    expect(screen.getByRole('heading', { name: /use cases/i })).toBeInTheDocument();
    expect(screen.getByText(/understanding fhir resource structures/i)).toBeInTheDocument();
  });

  it('should have proper structure with sections', () => {
    render(<AboutPage />);
    const sections = screen.getAllByRole('heading', { level: 2 });
    expect(sections).toHaveLength(4);
  });
});
