import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import Propositions from './Propositions'
import * as api from '../services/api'

describe('Propositions', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(api, 'adminListThemes').mockResolvedValue([])
  })

  it('disables the submit button until question, correct answer and difficulty are filled', async () => {
    render(<Propositions />)

    const submitButton = screen.getByRole('button', { name: 'Valider' })
    expect(submitButton).toBeDisabled()

    fireEvent.change(screen.getByLabelText('Question *'), { target: { value: 'Capitale de la France ?' } })
    fireEvent.change(screen.getByLabelText('Bonne réponse *'), { target: { value: 'Paris' } })
    expect(submitButton).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: 'Facile' }))
    expect(submitButton).not.toBeDisabled()
  })

  it('shows a confirmation and resets the form on successful submission', async () => {
    const submitSpy = vi.spyOn(api, 'submitProposition').mockResolvedValue({
      id: 1,
      text: 'Capitale de la France ?',
      correct_answer: 'Paris',
      wrong_answers: [],
      theme_id: null,
      difficulty: 'easy',
      status: 'pending',
      rejection_reason: null,
      created_at: '2026-07-29T00:00:00',
    })

    render(<Propositions />)
    fireEvent.change(screen.getByLabelText('Question *'), { target: { value: 'Capitale de la France ?' } })
    fireEvent.change(screen.getByLabelText('Bonne réponse *'), { target: { value: 'Paris' } })
    fireEvent.click(screen.getByRole('button', { name: 'Facile' }))
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }))

    await waitFor(() => {
      expect(screen.getByText(/sera vérifiée avant d'être ajoutée au jeu/)).toBeInTheDocument()
    })
    expect(submitSpy).toHaveBeenCalledTimes(1)
    expect((screen.getByLabelText('Question *') as HTMLInputElement).value).toBe('')
  })

  it('shows an error and keeps the entered values on submission failure', async () => {
    vi.spyOn(api, 'submitProposition').mockRejectedValue(new Error('Erreur réseau'))

    render(<Propositions />)
    fireEvent.change(screen.getByLabelText('Question *'), { target: { value: 'Capitale de la France ?' } })
    fireEvent.change(screen.getByLabelText('Bonne réponse *'), { target: { value: 'Paris' } })
    fireEvent.click(screen.getByRole('button', { name: 'Facile' }))
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }))

    await waitFor(() => {
      expect(screen.getByText('Erreur réseau')).toBeInTheDocument()
    })
    expect((screen.getByLabelText('Question *') as HTMLInputElement).value).toBe('Capitale de la France ?')
  })

  it('filters out blank wrong answers and threads the selected theme_id into the submitted payload', async () => {
    vi.spyOn(api, 'adminListThemes').mockResolvedValue([
      { id: 7, name: 'Cinéma', category: 'pop_culture', difficulty_level: 3, created_at: '2026-07-01' },
    ])
    const submitSpy = vi.spyOn(api, 'submitProposition').mockResolvedValue({
      id: 2,
      text: 'Q',
      correct_answer: 'A',
      wrong_answers: ['B'],
      theme_id: 7,
      difficulty: 'easy',
      status: 'pending',
      rejection_reason: null,
      created_at: '2026-07-29T00:00:00',
    })

    render(<Propositions />)
    await screen.findByText('Cinéma')

    fireEvent.change(screen.getByLabelText('Question *'), { target: { value: 'Q' } })
    fireEvent.change(screen.getByLabelText('Bonne réponse *'), { target: { value: 'A' } })
    fireEvent.change(screen.getByLabelText('Mauvaise réponse 1'), { target: { value: 'B' } })
    fireEvent.change(screen.getByLabelText('Mauvaise réponse 2'), { target: { value: '   ' } })
    fireEvent.change(screen.getByLabelText('Thème'), { target: { value: '7' } })
    fireEvent.click(screen.getByRole('button', { name: 'Facile' }))
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }))

    await waitFor(() => expect(submitSpy).toHaveBeenCalledTimes(1))
    expect(submitSpy).toHaveBeenCalledWith({
      text: 'Q',
      correct_answer: 'A',
      wrong_answers: ['B'],
      theme_id: 7,
      difficulty: 'easy',
    })
  })

  it('does not block the form when the theme list fails to load', async () => {
    vi.spyOn(api, 'adminListThemes').mockRejectedValue(new Error('Erreur réseau'))

    render(<Propositions />)

    fireEvent.change(screen.getByLabelText('Question *'), { target: { value: 'Q' } })
    fireEvent.change(screen.getByLabelText('Bonne réponse *'), { target: { value: 'A' } })
    fireEvent.click(screen.getByRole('button', { name: 'Facile' }))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Valider' })).not.toBeDisabled())
    expect(screen.getByLabelText('Thème')).toHaveValue('')
  })
})
