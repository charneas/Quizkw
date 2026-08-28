import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import Home from './Home'
import Game from './Game'
import AccountButton from '../components/AccountButton'
import * as api from '../services/api'
import { DiscordAccountProvider } from '../contexts/DiscordAccountContext'

function renderHome(initialPath = '/') {
  return render(
    <DiscordAccountProvider>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/" element={<Home />} />
        </Routes>
      </MemoryRouter>
    </DiscordAccountProvider>
  )
}

describe('Home — bouton Connexion Discord (Story O.1.1)', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.spyOn(api, 'fetchDiscordAccount').mockResolvedValue(null)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('affiche le bouton Connexion et le texte RGPD quand non connecté', async () => {
    renderHome()
    expect(await screen.findByRole('button', { name: 'Connexion' })).toBeInTheDocument()
    expect(
      screen.getByText(/Quizkw conserve ton identifiant, ton pseudo et ton avatar Discord/)
    ).toBeInTheDocument()
  })

  it('navigue en plein navigateur vers /api/auth/discord/login au clic', async () => {
    renderHome()
    const originalLocation = window.location
    try {
      // @ts-expect-error -- remplacement volontaire pour observer la navigation plein-navigateur
      delete window.location
      window.location = { ...originalLocation, href: '' } as Location

      fireEvent.click(await screen.findByRole('button', { name: 'Connexion' }))
      expect(window.location.href).toBe('/api/auth/discord/login')
    } finally {
      // Restauration systématique, même si l'assertion ci-dessus échoue --
      // sinon window.location reste un objet corrompu pour les tests suivants
      // du fichier (trouvé en revue de code).
      window.location = originalLocation
    }
  })

  it("masque le bouton Connexion quand un compte Discord est déjà connecté (Story O.1.2)", async () => {
    vi.spyOn(api, 'fetchDiscordAccount').mockResolvedValue({ pseudo: 'Test', avatar: 'https://cdn.discordapp.com/embed/avatars/0.png' })
    renderHome()
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Connexion' })).not.toBeInTheDocument())
  })

  it("n'affiche jamais le bouton Connexion en flash pour un utilisateur déjà connecté", async () => {
    // Revue de code : account vaut null jusqu'à la résolution de GET
    // /auth/discord/me, indiscernable de "non connecté" sans état de
    // chargement dédié — un compte déjà connecté voyait "Connexion"
    // apparaître puis disparaître à chaque montage.
    let resolveAccount!: (value: { pseudo: string; avatar: string }) => void
    vi.spyOn(api, 'fetchDiscordAccount').mockReturnValue(
      new Promise((resolve) => {
        resolveAccount = resolve
      })
    )
    renderHome()

    expect(screen.queryByRole('button', { name: 'Connexion' })).not.toBeInTheDocument()

    resolveAccount({ pseudo: 'Test', avatar: 'https://cdn.discordapp.com/embed/avatars/0.png' })
    await waitFor(() => expect(api.fetchDiscordAccount).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: 'Connexion' })).not.toBeInTheDocument()
  })

  it('retire ?discord=connected de la barre d\'adresse au montage (Story O.1.2)', async () => {
    // Revue de code : ce nettoyage avait disparu avec le retrait du flag
    // localStorage d'O.1.1, laissant le paramètre en permanence dans l'URL.
    window.history.pushState({}, '', '/?discord=connected')
    try {
      renderHome()
      await waitFor(() => expect(window.location.search).toBe(''))
    } finally {
      window.history.pushState({}, '', '/')
    }
  })
})

describe('Home + AccountButton — état partagé (Story O.2.1, revue de code)', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('la déconnexion via AccountButton fait réapparaître le bouton Connexion de Home sans reload', async () => {
    vi.spyOn(api, 'fetchDiscordAccount').mockResolvedValue({
      pseudo: 'Test',
      avatar: 'https://cdn.discordapp.com/embed/avatars/0.png',
    })
    vi.spyOn(api, 'logoutDiscord').mockResolvedValue(true)

    render(
      <DiscordAccountProvider>
        <MemoryRouter initialEntries={['/']}>
          <AccountButton />
          <Routes>
            <Route path="/" element={<Home />} />
          </Routes>
        </MemoryRouter>
      </DiscordAccountProvider>
    )

    const accountButton = await screen.findByRole('button', { name: /Test/ })
    expect(screen.queryByRole('button', { name: 'Connexion' })).not.toBeInTheDocument()

    fireEvent.click(accountButton)
    fireEvent.click(await screen.findByRole('button', { name: 'Se déconnecter' }))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Connexion' })).toBeInTheDocument())
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
