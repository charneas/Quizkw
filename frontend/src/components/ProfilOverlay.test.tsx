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

const STATS_WITH_DATA = {
  general: { personal_correct: 7, personal_total: 10, global_correct: 5, global_total: 10 },
  themes: [
    {
      theme_id: 1,
      theme_name: 'Cinéma',
      personal_correct: 7,
      personal_total: 10,
      global_correct: 5,
      global_total: 10,
      insufficient_data: false,
    },
    {
      theme_id: 2,
      theme_name: 'Sport',
      personal_correct: 2,
      personal_total: 3,
      global_correct: 1,
      global_total: 3,
      insufficient_data: true,
    },
  ],
}

const STATS_EMPTY = {
  general: { personal_correct: 0, personal_total: 0, global_correct: 0, global_total: 0 },
  themes: [],
}

async function openProfil() {
  const account = { pseudo: 'TestPlayer', avatar: 'https://cdn.discordapp.com/embed/avatars/0.png' }
  vi.spyOn(api, 'fetchDiscordAccount').mockResolvedValue(account)
  renderAccountButton()
  fireEvent.click(await screen.findByRole('button', { name: /TestPlayer/ }))
  fireEvent.click(await screen.findByRole('button', { name: 'Voir mes statistiques' }))
  return screen.findByRole('dialog')
}

describe('ProfilOverlay (Story O.2.2)', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('ouvre un dialog accessible (role=dialog, aria-modal) depuis le menu du compte', async () => {
    vi.spyOn(api, 'fetchAccountStats').mockResolvedValue(STATS_WITH_DATA)
    const dialog = await openProfil()
    expect(dialog).toHaveAttribute('aria-modal', 'true')
  })

  it('Échap ferme l\'overlay et rend le focus au bouton déclencheur', async () => {
    vi.spyOn(api, 'fetchAccountStats').mockResolvedValue(STATS_WITH_DATA)
    await openProfil()

    fireEvent.keyDown(document, { key: 'Escape' })

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: /TestPlayer/ })).toHaveFocus()
  })

  it('rend le contenu applicatif sous-jacent inert pendant l\'ouverture', async () => {
    const appRoot = document.createElement('div')
    document.getElementById('root')?.remove()
    const rootEl = document.createElement('div')
    rootEl.id = 'root'
    rootEl.appendChild(appRoot)
    document.body.appendChild(rootEl)

    vi.spyOn(api, 'fetchAccountStats').mockResolvedValue(STATS_WITH_DATA)
    await openProfil()

    await waitFor(() => expect(appRoot.inert).toBe(true))

    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(appRoot.inert).toBe(false))

    rootEl.remove()
  })

  it('affiche un message neutre pour un thème sous le seuil, sans barre', async () => {
    vi.spyOn(api, 'fetchAccountStats').mockResolvedValue(STATS_WITH_DATA)
    await openProfil()

    expect(
      await screen.findByText(/Sport — Pas encore assez de réponses sur ce thème/)
    ).toBeInTheDocument()
  })

  it('affiche un message neutre pour la stat générale sans aucune donnée (compte neuf)', async () => {
    vi.spyOn(api, 'fetchAccountStats').mockResolvedValue(STATS_EMPTY)
    await openProfil()

    expect(await screen.findByText(/Pas encore de partie jouée en étant connecté/)).toBeInTheDocument()
  })

  it('affiche les valeurs numériques en texte visible pour un thème avec assez de données', async () => {
    vi.spyOn(api, 'fetchAccountStats').mockResolvedValue(STATS_WITH_DATA)
    await openProfil()

    const matches = await screen.findAllByText('Toi : 70 % · Moyenne : 50 %')
    expect(matches.length).toBeGreaterThanOrEqual(1)
  })
})
