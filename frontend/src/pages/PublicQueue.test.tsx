import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import PublicQueue from './PublicQueue'
import * as api from '../services/api'

function renderQueue(code = 'ABC123') {
  return render(
    <MemoryRouter initialEntries={[`/public-queue/${code}`]}>
      <Routes>
        <Route path="/public-queue/:code" element={<PublicQueue />} />
        <Route path="/" element={<div>Accueil</div>} />
      </Routes>
    </MemoryRouter>
  )
}

describe('PublicQueue — bouton Annuler (spec-public-queue-leave)', () => {
  beforeEach(() => {
    vi.spyOn(api, 'getGame').mockResolvedValue({ started: false, teams: [{}, {}] })
    vi.spyOn(api, 'getPlayerIdentity').mockReturnValue({ id: 7, name: 'Alice', team_id: 42 })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("appelle leavePublicQueue avec le code et le team_id puis revient à l'accueil", async () => {
    const leave = vi.spyOn(api, 'leavePublicQueue').mockResolvedValue()
    renderQueue()

    fireEvent.click(await screen.findByRole('button', { name: /Annuler/ }))

    expect(await screen.findByText('Accueil')).toBeInTheDocument()
    expect(api.getPlayerIdentity).toHaveBeenCalledWith('ABC123')
    expect(leave).toHaveBeenCalledWith('ABC123', 42)
  })

  it("revient à l'accueil même si leavePublicQueue échoue", async () => {
    vi.spyOn(api, 'leavePublicQueue').mockRejectedValue(new Error('409'))
    renderQueue()

    fireEvent.click(await screen.findByRole('button', { name: /Annuler/ }))

    expect(await screen.findByText('Accueil')).toBeInTheDocument()
  })

  it("désactive le bouton pendant l'appel", async () => {
    let resolveLeave: () => void = () => {}
    vi.spyOn(api, 'leavePublicQueue').mockImplementation(
      () => new Promise<void>((resolve) => { resolveLeave = resolve })
    )
    renderQueue()

    fireEvent.click(await screen.findByRole('button', { name: /Annuler/ }))

    const button = await screen.findByRole('button', { name: /Annulation/ })
    expect(button).toBeDisabled()

    resolveLeave()
    await waitFor(() => expect(screen.getByText('Accueil')).toBeInTheDocument())
  })
})
