import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import Home from './Home'
import Game from './Game'
import * as api from '../services/api'

function renderHome(initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/" element={<Home />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('Home — bouton Connexion Discord (Story O.1.1)', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('affiche le bouton Connexion et le texte RGPD quand non connecté', () => {
    renderHome()
    expect(screen.getByRole('button', { name: 'Connexion' })).toBeInTheDocument()
    expect(
      screen.getByText(/Quizkw conserve ton identifiant, ton pseudo et ton avatar Discord/)
    ).toBeInTheDocument()
  })

  it('navigue en plein navigateur vers /api/auth/discord/login au clic', () => {
    renderHome()
    const originalLocation = window.location
    try {
      // @ts-expect-error -- remplacement volontaire pour observer la navigation plein-navigateur
      delete window.location
      window.location = { ...originalLocation, href: '' } as Location

      fireEvent.click(screen.getByRole('button', { name: 'Connexion' }))
      expect(window.location.href).toBe('/api/auth/discord/login')
    } finally {
      // Restauration systématique, même si l'assertion ci-dessus échoue --
      // sinon window.location reste un objet corrompu pour les tests suivants
      // du fichier (trouvé en revue de code).
      window.location = originalLocation
    }
  })

  it('affiche l\'état connecté après retour du callback (?discord=connected) et le mémorise', () => {
    // Home.tsx lit window.location.search (redirection plein-navigateur réelle
    // depuis le backend), pas la route virtuelle de MemoryRouter.
    window.history.pushState({}, '', '/?discord=connected')
    try {
      renderHome()
      expect(screen.getByText('Connecté')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Connexion' })).not.toBeInTheDocument()
      expect(localStorage.getItem('quizkw_discord_connected')).toBe('true')
    } finally {
      window.history.pushState({}, '', '/')
    }
  })

  it('reste connecté après un rechargement (flag localStorage)', () => {
    localStorage.setItem('quizkw_discord_connected', 'true')
    renderHome()
    expect(screen.getByText('Connecté')).toBeInTheDocument()
  })
})

describe('Game — non-régression : bouton Connexion absent en partie', () => {
  beforeEach(() => {
    vi.spyOn(api, 'getGame').mockRejectedValue(new Error('not needed for this check'))
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("n'affiche jamais le bouton Connexion Discord sur une page de jeu", () => {
    render(
      <MemoryRouter initialEntries={['/game/TEST123']}>
        <Routes>
          <Route path="/game/:code" element={<Game />} />
        </Routes>
      </MemoryRouter>
    )
    expect(screen.queryByRole('button', { name: 'Connexion' })).not.toBeInTheDocument()
  })
})
