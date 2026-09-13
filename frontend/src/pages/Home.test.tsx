import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
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
      window.location = { ...originalLocation, href: '' } as unknown as string & Location

      fireEvent.click(await screen.findByRole('button', { name: 'Connexion' }))
      expect(window.location.href).toBe('/api/auth/discord/login')
    } finally {
      // Restauration systématique, même si l'assertion ci-dessus échoue --
      // sinon window.location reste un objet corrompu pour les tests suivants
      // du fichier (trouvé en revue de code).
      window.location = originalLocation as unknown as string & Location
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

describe('Home — carte Blindtest (spec-blindtest-integration-ui, story 1)', () => {
  beforeEach(() => {
    vi.spyOn(api, 'fetchDiscordAccount').mockResolvedValue(null)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  function renderHomeWithBlindtestRoute() {
    return render(
      <DiscordAccountProvider>
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/blindtest/:code" element={<p>Blindtest lobby page</p>} />
          </Routes>
        </MemoryRouter>
      </DiscordAccountProvider>
    )
  }

  function getBlindtestCard() {
    const heading = screen.getByText('🎵 Blindtest')
    return heading.closest('.card') as HTMLElement
  }

  it('désactive le bouton Rejoindre tant que le code est vide', async () => {
    renderHomeWithBlindtestRoute()
    const card = getBlindtestCard()
    expect(await within(card).findByRole('button', { name: 'Rejoindre' })).toBeDisabled()
  })

  it('navigue vers /blindtest/<CODE> (majuscule) au clic sur Rejoindre', async () => {
    renderHomeWithBlindtestRoute()
    const card = getBlindtestCard()
    const input = within(card).getByPlaceholderText('Code de la partie')
    const button = within(card).getByRole('button', { name: 'Rejoindre' })

    fireEvent.change(input, { target: { value: 'abc123' } })
    expect(button).not.toBeDisabled()
    fireEvent.click(button)

    expect(await screen.findByText('Blindtest lobby page')).toBeInTheDocument()
  })

  it('navigue vers /blindtest/<CODE> à la touche Entrée', async () => {
    renderHomeWithBlindtestRoute()
    const card = getBlindtestCard()
    const input = within(card).getByPlaceholderText('Code de la partie')

    fireEvent.change(input, { target: { value: 'xyz789' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    expect(await screen.findByText('Blindtest lobby page')).toBeInTheDocument()
  })

  it('crée une partie blindtest et navigue vers /blindtest/<code> retourné par le backend (story 2)', async () => {
    vi.spyOn(api, 'createBlindtestGame').mockResolvedValue({ id: 1, code: 'ZQ7K2P' })
    renderHomeWithBlindtestRoute()
    const card = getBlindtestCard()
    const button = within(card).getByRole('button', { name: 'Créer une partie' })

    fireEvent.click(button)

    expect(await screen.findByText('Blindtest lobby page')).toBeInTheDocument()
  })

  it("affiche une erreur inline et réactive le bouton quand la création échoue (story 2)", async () => {
    vi.spyOn(api, 'createBlindtestGame').mockRejectedValue(new Error('Erreur serveur'))
    renderHomeWithBlindtestRoute()
    const card = getBlindtestCard()
    const button = within(card).getByRole('button', { name: 'Créer une partie' })

    fireEvent.click(button)

    expect(await within(card).findByText('Erreur serveur')).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Créer une partie' })).not.toBeDisabled()
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
