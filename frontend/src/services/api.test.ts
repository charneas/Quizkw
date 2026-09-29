import { describe, it, expect, vi, afterEach } from 'vitest'
import { formatErrorDetail, getGame } from './api'

describe('formatErrorDetail', () => {
  it('garde un detail texte (message métier du backend)', () => {
    expect(formatErrorDetail('Session de jeu non trouvée', 404)).toBe('Session de jeu non trouvée')
  })

  it('remplace une liste de validation Pydantic (422) par un message lisible', () => {
    const detail = [{ type: 'greater_than', loc: ['body', 'total_players'], msg: 'Input should be greater than 0' }]
    expect(formatErrorDetail(detail, 422)).toBe('Données invalides.')
  })

  it('remplace un detail objet par un message lisible', () => {
    expect(formatErrorDetail({ code: 'x' }, 400)).toBe('Données invalides.')
  })

  it('retombe sur "Erreur <status>" si detail est absent ou vide', () => {
    expect(formatErrorDetail(undefined, 500)).toBe('Erreur 500')
    expect(formatErrorDetail(null, 500)).toBe('Erreur 500')
    expect(formatErrorDetail('', 500)).toBe('Erreur 500')
    expect(formatErrorDetail([], 422)).toBe('Erreur 422')
  })
})

describe('fetchApi — erreurs', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function stubFetch(status: number, body: unknown) {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status, json: () => Promise.resolve(body) }),
    )
  }

  it("n'affiche jamais [object Object] sur une 422", async () => {
    stubFetch(422, { detail: [{ loc: ['path', 'code'], msg: 'Field required', type: 'missing' }] })
    await expect(getGame('ABC')).rejects.toThrow('Données invalides.')
  })

  it('propage un detail texte tel quel', async () => {
    stubFetch(404, { detail: 'Session de jeu non trouvée' })
    await expect(getGame('ABC')).rejects.toThrow('Session de jeu non trouvée')
  })
})
