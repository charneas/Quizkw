import { describe, it, expect } from 'vitest'
import { pluralJoueurs } from './pluralize'

describe('pluralJoueurs', () => {
  it('returns the singular form for 1', () => {
    expect(pluralJoueurs(1)).toBe('joueur')
  })

  it('returns the plural form for counts above 1', () => {
    expect(pluralJoueurs(2)).toBe('joueurs')
    expect(pluralJoueurs(3)).toBe('joueurs')
  })
})
