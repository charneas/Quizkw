import { useEffect, useState } from 'react'
import AdminLayout from '../components/AdminLayout'
import type { QuestionStatsListItem, ThemeStatsResponse } from '../types'
import { adminGetAllQuestionStats, adminGetThemeStats } from '../services/api'

type Tab = 'themes' | 'questions'
type ThemeSortKey = 'theme_name' | 'questions_count' | 'times_answered' | 'success_rate'
type QuestionSortKey = 'text' | 'theme_name' | 'times_answered' | 'success_rate'

export default function AdminStats() {
  const [tab, setTab] = useState<Tab>('themes')
  const [themeStats, setThemeStats] = useState<ThemeStatsResponse[]>([])
  const [questionStats, setQuestionStats] = useState<QuestionStatsListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [themeSortKey, setThemeSortKey] = useState<ThemeSortKey>('theme_name')
  const [themeSortAsc, setThemeSortAsc] = useState(true)
  const [questionSortKey, setQuestionSortKey] = useState<QuestionSortKey>('times_answered')
  const [questionSortAsc, setQuestionSortAsc] = useState(false)

  async function refresh() {
    setLoading(true)
    setError(null)
    try {
      const [themes, questions] = await Promise.all([adminGetThemeStats(), adminGetAllQuestionStats()])
      setThemeStats(themes)
      setQuestionStats(questions)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  function toggleThemeSort(key: ThemeSortKey) {
    if (key === themeSortKey) setThemeSortAsc(!themeSortAsc)
    else {
      setThemeSortKey(key)
      setThemeSortAsc(true)
    }
  }

  function toggleQuestionSort(key: QuestionSortKey) {
    if (key === questionSortKey) setQuestionSortAsc(!questionSortAsc)
    else {
      setQuestionSortKey(key)
      setQuestionSortAsc(true)
    }
  }

  const sortedThemes = [...themeStats].sort((a, b) => {
    let cmp: number
    if (themeSortKey === 'theme_name') cmp = a.theme_name.localeCompare(b.theme_name)
    else cmp = a[themeSortKey] - b[themeSortKey]
    return themeSortAsc ? cmp : -cmp
  })

  const sortedQuestions = [...questionStats].sort((a, b) => {
    let cmp: number
    if (questionSortKey === 'text') cmp = a.text.localeCompare(b.text)
    else if (questionSortKey === 'theme_name') cmp = (a.theme_name ?? '').localeCompare(b.theme_name ?? '')
    else cmp = a[questionSortKey] - b[questionSortKey]
    return questionSortAsc ? cmp : -cmp
  })

  return (
    <AdminLayout>
      <div className="p-6 max-w-6xl mx-auto space-y-4 text-text">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Statistiques</h1>
          <button className="btn-secondary" onClick={refresh}>Rafraîchir</button>
        </div>

        {error && <div className="bg-surface-raised text-danger p-3 rounded-lg border border-danger">{error}</div>}

        <div className="flex gap-2">
          <button
            className={`px-4 py-2 rounded-lg text-sm ${tab === 'themes' ? 'bg-brand-600 text-white' : 'bg-surface-raised text-text-muted'}`}
            onClick={() => setTab('themes')}
          >
            Par thème
          </button>
          <button
            className={`px-4 py-2 rounded-lg text-sm ${tab === 'questions' ? 'bg-brand-600 text-white' : 'bg-surface-raised text-text-muted'}`}
            onClick={() => setTab('questions')}
          >
            Par question
          </button>
        </div>

        {loading ? (
          <p className="text-text-muted">Chargement...</p>
        ) : tab === 'themes' ? (
          <div className="card overflow-x-auto">
            {sortedThemes.length === 0 ? (
              <p className="text-text-muted">Aucun thème.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left border-b border-border">
                    <th className="p-2 cursor-pointer" onClick={() => toggleThemeSort('theme_name')}>Thème</th>
                    <th className="p-2 cursor-pointer" onClick={() => toggleThemeSort('questions_count')}>Questions</th>
                    <th className="p-2 cursor-pointer" onClick={() => toggleThemeSort('times_answered')}>Réponses reçues</th>
                    <th className="p-2 cursor-pointer" onClick={() => toggleThemeSort('success_rate')}>Taux de réussite</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedThemes.map((t) => (
                    <tr key={t.theme_id} className="border-b border-border">
                      <td className="p-2">{t.theme_name}</td>
                      <td className="p-2">
                        {t.questions_count}
                        {t.questions_count < 10 && (
                          <span className="ml-1 text-danger" title="Sous le seuil de 10 questions requis pour être utilisable en jeu">⚠</span>
                        )}
                      </td>
                      <td className="p-2">{t.times_answered}</td>
                      <td className="p-2">{t.times_answered > 0 ? `${Math.round(t.success_rate * 100)}%` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ) : (
          <div className="card overflow-x-auto">
            {sortedQuestions.length === 0 ? (
              <p className="text-text-muted">Aucune question.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left border-b border-border">
                    <th className="p-2 cursor-pointer" onClick={() => toggleQuestionSort('text')}>Question</th>
                    <th className="p-2 cursor-pointer" onClick={() => toggleQuestionSort('theme_name')}>Thème</th>
                    <th className="p-2 cursor-pointer" onClick={() => toggleQuestionSort('times_answered')}>Réponses reçues</th>
                    <th className="p-2 cursor-pointer" onClick={() => toggleQuestionSort('success_rate')}>Taux de réussite</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedQuestions.map((q) => (
                    <tr key={q.question_id} className="border-b border-border">
                      <td className="p-2">{q.text}</td>
                      <td className="p-2">{q.theme_name ?? 'Sans thème'}</td>
                      <td className="p-2">{q.times_answered}</td>
                      <td className="p-2">{q.times_answered > 0 ? `${Math.round(q.success_rate * 100)}%` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
