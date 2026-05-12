import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ThemeSelector from './ThemeSelector';
import type { Theme } from '../types';

describe('ThemeSelector', () => {
  const mockThemes: Theme[] = [
    { id: 1, name: 'Science', category: 'serious', difficulty_level: 5, description: 'Desc 1', created_at: '2026-05-01' },
    { id: 2, name: 'Movies', category: 'pop_culture', difficulty_level: 8, description: 'Desc 2', created_at: '2026-05-01' },
    { id: 3, name: 'History', category: 'whimsical', difficulty_level: 2, description: 'Desc 3', created_at: '2026-05-01' },
  ];

  const mockOnSelectTheme = vi.fn();

  it('renders correctly with themes', () => {
    render(<ThemeSelector themes={mockThemes} onSelectTheme={mockOnSelectTheme} gameCode="ABC" />);
    
    expect(screen.getByText('Choose Your Theme')).toBeInTheDocument();
    expect(screen.getByText('Science')).toBeInTheDocument();
    expect(screen.getByText('Movies')).toBeInTheDocument();
    expect(screen.getByText('History')).toBeInTheDocument();
  });

  it('calls onSelectTheme when a theme is clicked', () => {
    render(<ThemeSelector themes={mockThemes} onSelectTheme={mockOnSelectTheme} gameCode="ABC" />);
    
    const themeCard = screen.getByText('Science');
    fireEvent.click(themeCard);
    
    expect(mockOnSelectTheme).toHaveBeenCalledWith(mockThemes[0]);
  });
});
