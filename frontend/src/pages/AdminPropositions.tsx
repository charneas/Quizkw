import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import type { Proposition, Difficulty } from '../types'
import { adminAcceptProposition, adminListPendingPropositions, adminRejectProposition } from '../services/api'
import AdminLayout from '../components/AdminLayout'

type SortKey = 'text' | 'theme' | 'difficulty'

const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  easy: 'Facile',
  medium: 'Moyen',
  hard: 'Difficile',
}

export default function AdminPropositions() {
  const [propositions, setPropositions] = useState<Proposition[]>([])
  const [error, setError] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('text')
  const [sortAsc, setSortAsc] = useState(true)

  const [message, setMessage] = useState<string | null>(null)

  async function refresh() {
    try {
      setPropositions(await adminListPendingPropositions())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  async function handleAccept(p: Proposition) {
    if (!window.confirm('Accepter cette proposition ? Elle deviendra une question jouable.')) return
    try {
      const result = await adminAcceptProposition(p.id)
      setMessage(result.message)
      setError(null)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function handleReject(p: Proposition) {
    const reason = window.prompt('Raison du refus (obligatoire) :')
    if (reason === null) return
    const trimmed = reason.trim()
    if (!trimmed) {
      window.alert('La raison de refus ne peut pas être vide.')
      return
    }
    if (trimmed.length > 500) {
      window.alert('La raison de refus ne peut pas dépasser 500 caractères.')
      return
    }
    if (!window.confirm('Refuser cette proposition ? Cette décision est définitive.')) return
    try {
      await adminRejectProposition(p.id, trimmed)
      setMessage('Proposition refusée.')
      setError(null)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortAsc(!sortAsc)
    } else {
      setSortKey(key)
      setSortAsc(true)
    }
  }

  const sorted = [...propositions].sort((a, b) => {
    let cmp: number
    if (sortKey === 'theme') {
      cmp = (a.theme_id ?? -1) - (b.theme_id ?? -1)
    } else if (sortKey === 'difficulty') {
      cmp = a.difficulty.localeCompare(b.difficulty)
    } else {
      cmp = a.text.localeCompare(b.text)
    }
    return sortAsc ? cmp : -cmp
  })

  return (
    <AdminLayout>
    <div>
      <div className="max-w-5xl mx-auto space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">Propositions en attente</h1>
          <button className="btn-secondary" onClick={refresh}>Rafraîchir</button>
        </div>

        {message && <p className="text-sm text-green-600">{message}</p>}
        {error && <p className="text-sm text-red-500">{error}</p>}

        <div className="card overflow-x-auto">
          {sorted.length === 0 ? (
            <p className="text-text-muted">Aucune proposition en attente.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left border-b border-border">
                  <th className="p-2 cursor-pointer" onClick={() => toggleSort('text')}>Question</th>
                  <th className="p-2">Bonne réponse</th>
                  <th className="p-2">Mauvaises réponses</th>
                  <th className="p-2 cursor-pointer" onClick={() => toggleSort('theme')}>Thème</th>
                  <th className="p-2 cursor-pointer" onClick={() => toggleSort('difficulty')}>Difficulté</th>
                  <th className="p-2"></th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((p) => (
                  <tr key={p.id} className="border-b border-border">
                    <td className="p-2">{p.text}</td>
                    <td className="p-2">{p.correct_answer}</td>
                    <td className="p-2">{p.wrong_answers.join(', ')}</td>
                    <td className="p-2">{p.theme_id === null ? 'À déterminer' : p.theme_id}</td>
                    <td className="p-2">{DIFFICULTY_LABELS[p.difficulty]}</td>
                    <td className="p-2 flex gap-3">
                      <Link to={`/admin/propositions/${p.id}/edit`} state={{ proposition: p }} className="text-brand hover:underline">
                        Éditer
                      </Link>
                      <button
                        className="text-brand hover:underline disabled:text-text-muted disabled:no-underline disabled:cursor-not-allowed"
                        disabled={p.theme_id === null}
                        onClick={() => handleAccept(p)}
                      >
                        Accepter
                      </button>
                      <button
                        className="text-danger hover:underline"
                        onClick={() => handleReject(p)}
                      >
                        Refuser
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
    </AdminLayout>
  )
}
