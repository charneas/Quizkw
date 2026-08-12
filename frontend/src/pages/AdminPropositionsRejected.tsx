import { useEffect, useState } from 'react'
import type { Proposition, Difficulty } from '../types'
import { adminListRejectedPropositions } from '../services/api'
import AdminLayout from '../components/AdminLayout'

type SortKey = 'text' | 'theme' | 'difficulty'

const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  easy: 'Facile',
  medium: 'Moyen',
  hard: 'Difficile',
}

export default function AdminPropositionsRejected() {
  const [propositions, setPropositions] = useState<Proposition[]>([])
  const [error, setError] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('text')
  const [sortAsc, setSortAsc] = useState(true)

  async function refresh() {
    try {
      setPropositions(await adminListRejectedPropositions())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    refresh()
  }, [])

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
          <h1 className="text-xl font-semibold">Propositions refusées</h1>
          <button className="btn-secondary" onClick={refresh}>Rafraîchir</button>
        </div>

        {error && <p className="text-sm text-red-500">{error}</p>}

        <div className="card overflow-x-auto">
          {sorted.length === 0 ? (
            <p className="text-text-muted">Aucune proposition refusée.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left border-b border-border">
                  <th className="p-2 cursor-pointer" onClick={() => toggleSort('text')}>Question</th>
                  <th className="p-2">Bonne réponse</th>
                  <th className="p-2">Mauvaises réponses</th>
                  <th className="p-2 cursor-pointer" onClick={() => toggleSort('theme')}>Thème</th>
                  <th className="p-2 cursor-pointer" onClick={() => toggleSort('difficulty')}>Difficulté</th>
                  <th className="p-2">Raison du refus</th>
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
                    <td className="p-2">{p.rejection_reason}</td>
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
