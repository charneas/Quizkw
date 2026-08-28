import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import AccountButton from './AccountButton'
import * as api from '../services/api'
import { DiscordAccountProvider } from '../contexts/DiscordAccountContext'

function renderAccountButton() {
  return render(
    <DiscordAccountProvider>
      <AccountButton />
    </DiscordAccountProvider>
  )
}

describe('AccountButton (Story O.1.2)', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("ne rend rien quand aucun compte Discord n'est connecté", async () => {
    vi.spyOn(api, 'fetchDiscordAccount').mockResolvedValue(null)
    const { container } = renderAccountButton()
    await waitFor(() => expect(api.fetchDiscordAccount).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it("reste non connecté sans rejection non gérée si l'appel réseau échoue", async () => {
    // Revue de code : fetchDiscordAccount().then(...) sans .catch() laissait
    // une rejection non gérée en cas d'erreur réseau/JSON inattendu.
    vi.spyOn(api, 'fetchDiscordAccount').mockRejectedValue(new Error('network down'))
    const { container } = renderAccountButton()
    await waitFor(() => expect(api.fetchDiscordAccount).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('affiche le pseudo + avatar quand un compte est connecté, zone cliquable >= 44px', async () => {
    vi.spyOn(api, 'fetchDiscordAccount').mockResolvedValue({
      pseudo: 'TestPlayer',
      avatar: 'https://cdn.discordapp.com/embed/avatars/0.png',
    })
    renderAccountButton()

    const button = await screen.findByRole('button', { name: /TestPlayer/ })
    expect(button).toBeInTheDocument()
    expect(button.className).toContain('min-h-[44px]')

    // alt="" est volontaire (avatar décoratif, DESIGN.md) — un tel <img> n'a
    // pas de rôle accessible "img", d'où une sélection directe ici.
    const avatar = button.querySelector('img')
    expect(avatar).toHaveAttribute('alt', '')
    expect(avatar).toHaveAttribute('src', 'https://cdn.discordapp.com/embed/avatars/0.png')
  })

  it('ouvre le menu et déclenche la déconnexion sans navigation/reload', async () => {
    vi.spyOn(api, 'fetchDiscordAccount').mockResolvedValue({
      pseudo: 'TestPlayer',
      avatar: 'https://cdn.discordapp.com/embed/avatars/0.png',
    })
    const logoutSpy = vi.spyOn(api, 'logoutDiscord').mockResolvedValue(true)

    const originalLocation = window.location
    try {
      // @ts-expect-error -- remplacement volontaire pour observer une absence de navigation
      delete window.location
      window.location = { ...originalLocation, href: '', reload: vi.fn() } as unknown as Location

      renderAccountButton()
      const button = await screen.findByRole('button', { name: /TestPlayer/ })
      fireEvent.click(button)

      const logoutButton = await screen.findByRole('button', { name: 'Se déconnecter' })
      fireEvent.click(logoutButton)

      await waitFor(() => expect(logoutSpy).toHaveBeenCalled())
      await waitFor(() => expect(screen.queryByRole('button', { name: /TestPlayer/ })).not.toBeInTheDocument())

      expect(window.location.href).toBe('')
      expect(window.location.reload).not.toHaveBeenCalled()
    } finally {
      window.location = originalLocation
    }
  })

  it('ne se déconnecte pas localement si le serveur refuse la déconnexion (429/5xx)', async () => {
    // Revue de code : sans vérifier response.ok, un logout raté côté serveur
    // laissait quand même disparaître le bouton connecté côté client.
    vi.spyOn(api, 'fetchDiscordAccount').mockResolvedValue({
      pseudo: 'TestPlayer',
      avatar: 'https://cdn.discordapp.com/embed/avatars/0.png',
    })
    const logoutSpy = vi.spyOn(api, 'logoutDiscord').mockResolvedValue(false)

    renderAccountButton()
    const button = await screen.findByRole('button', { name: /TestPlayer/ })
    fireEvent.click(button)
    fireEvent.click(await screen.findByRole('button', { name: 'Se déconnecter' }))

    await waitFor(() => expect(logoutSpy).toHaveBeenCalled())
    expect(screen.getByRole('button', { name: /TestPlayer/ })).toBeInTheDocument()
  })

  it('affiche un message quand la déconnexion échoue, effacé à la réouverture du menu', async () => {
    vi.spyOn(api, 'fetchDiscordAccount').mockResolvedValue({
      pseudo: 'TestPlayer',
      avatar: 'https://cdn.discordapp.com/embed/avatars/0.png',
    })
    vi.spyOn(api, 'logoutDiscord').mockResolvedValue(false)

    renderAccountButton()
    const button = await screen.findByRole('button', { name: /TestPlayer/ })
    fireEvent.click(button)
    fireEvent.click(await screen.findByRole('button', { name: 'Se déconnecter' }))

    expect(await screen.findByText(/Déconnexion impossible/)).toBeInTheDocument()

    // Referme puis rouvre le menu : le message ne doit pas rester affiché
    // indéfiniment après un nouvel essai potentiel.
    fireEvent.click(button)
    fireEvent.click(button)
    expect(screen.queryByText(/Déconnexion impossible/)).not.toBeInTheDocument()
  })

  describe('Suppression de compte (Story O.3.1)', () => {
    async function openMenu() {
      vi.spyOn(api, 'fetchDiscordAccount').mockResolvedValue({
        pseudo: 'TestPlayer',
        avatar: 'https://cdn.discordapp.com/embed/avatars/0.png',
      })
      renderAccountButton()
      const button = await screen.findByRole('button', { name: /TestPlayer/ })
      fireEvent.click(button)
    }

    it('affiche une confirmation avant toute suppression effective', async () => {
      const deleteSpy = vi.spyOn(api, 'deleteAccount')
      await openMenu()

      fireEvent.click(await screen.findByRole('button', { name: 'Supprimer mon compte' }))

      expect(await screen.findByText(/Cette action est définitive/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Supprimer définitivement' })).toBeInTheDocument()
      expect(deleteSpy).not.toHaveBeenCalled()
    })

    it("supprime le compte et fait disparaître le bouton quand le serveur confirme", async () => {
      const deleteSpy = vi.spyOn(api, 'deleteAccount').mockResolvedValue(true)
      await openMenu()

      fireEvent.click(await screen.findByRole('button', { name: 'Supprimer mon compte' }))
      fireEvent.click(await screen.findByRole('button', { name: 'Supprimer définitivement' }))

      await waitFor(() => expect(deleteSpy).toHaveBeenCalled())
      await waitFor(() => expect(screen.queryByRole('button', { name: /TestPlayer/ })).not.toBeInTheDocument())
    })

    it('ne supprime pas localement si le serveur refuse (429/5xx)', async () => {
      const deleteSpy = vi.spyOn(api, 'deleteAccount').mockResolvedValue(false)
      await openMenu()

      fireEvent.click(await screen.findByRole('button', { name: 'Supprimer mon compte' }))
      fireEvent.click(await screen.findByRole('button', { name: 'Supprimer définitivement' }))

      await waitFor(() => expect(deleteSpy).toHaveBeenCalled())
      expect(screen.getByRole('button', { name: /TestPlayer/ })).toBeInTheDocument()
    })

    it('affiche un message dans la confirmation quand la suppression échoue', async () => {
      vi.spyOn(api, 'deleteAccount').mockResolvedValue(false)
      await openMenu()

      fireEvent.click(await screen.findByRole('button', { name: 'Supprimer mon compte' }))
      fireEvent.click(await screen.findByRole('button', { name: 'Supprimer définitivement' }))

      expect(await screen.findByText(/Suppression impossible/)).toBeInTheDocument()
      // La confirmation reste ouverte : le message doit rester visible avec elle.
      expect(screen.getByRole('button', { name: 'Supprimer définitivement' })).toBeInTheDocument()
    })

    it("l'annulation ferme la confirmation sans appeler l'API", async () => {
      const deleteSpy = vi.spyOn(api, 'deleteAccount')
      await openMenu()

      fireEvent.click(await screen.findByRole('button', { name: 'Supprimer mon compte' }))
      fireEvent.click(await screen.findByRole('button', { name: 'Annuler' }))

      await waitFor(() =>
        expect(screen.queryByRole('button', { name: 'Supprimer définitivement' })).not.toBeInTheDocument()
      )
      expect(deleteSpy).not.toHaveBeenCalled()
    })
  })
})
