// On cible le port 8000 du backend Python
const API_BASE = 'http://localhost:8000'

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Erreur réseau' }))
    throw new Error(error.detail || `Erreur ${response.status}`)
  }

  return response.json()
}

// === Sessions de jeu ===

export async function createGame(data: any) {
  return fetchApi<any>('/games/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getGame(code: string) {
  return fetchApi<any>(`/games/${code}`)
}

export async function startGame(code: string) {
  return fetchApi<any>(`/games/${code}/start`, {
    method: 'POST',
  })
}

// === Équipes et Joueurs ===

export async function createTeam(gameCode: string, data: any) {
  return fetchApi<any>(`/games/${gameCode}/teams/`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function createPlayer(gameCode: string, data: { name: string }) {
  return fetchApi<any>(`/games/${gameCode}/players/`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// === Jetons (Tokens) ===

export async function getTeamTokens(teamId: number) {
  const data = await fetchApi<any>(`/teams/${teamId}/tokens`)
  if (data && data.tokens) {
    return data.tokens
  }
  return data
}

export async function useToken(data: { team_id: number; token_type: string }) {
  return fetchApi<any>('/tokens/use', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// === Déroulement du jeu (Manche 1) ===

export async function getRandomQuestion() {
  return fetchApi<any>('/questions/random')
}

export async function setCurrentQuestion(gameCode: string, questionId: number) {
  return fetchApi<any>(`/games/${gameCode}/set-current-question`, {
    method: 'POST',
    body: JSON.stringify({ question_id: questionId }),
  })
}

export async function getCurrentQuestion(gameCode: string) {
  return fetchApi<any>(`/games/${gameCode}/current-question`)
}

export async function getAnswersStatus(gameCode: string) {
  return fetchApi<any>(`/games/${gameCode}/answers-status`)
}

export async function submitAnswer(data: any) {
  return fetchApi<any>('/answers/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// === Roue Bonus/Malus ===

export async function spinWheel(teamId: number) {
  return fetchApi<any>('/wheel/spin', {
    method: 'POST',
    body: JSON.stringify({ team_id: teamId }),
  })
}

// === Manche 2 (Tournoi) ===

// CORRECTION DES EXPORTS POUR S'ALIGNER AVEC ROUND2.TSX
export async function getRound2Themes(gameCode: string) {
  return fetchApi<any>(`/round2/${gameCode}/themes`)
}
export { getRound2Themes as getThemes }

export async function selectRound2Theme(gameCode: string, data: { player_id: number; theme_id: number }) {
  return fetchApi<any>(`/round2/${gameCode}/select-theme`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}
export { selectRound2Theme as selectTheme }

export async function getRound2Question(gameCode: string, playerId: number) {
  return fetchApi<any>(`/round2/${gameCode}/question?player_id=${playerId}`)
}
export { getRound2Question as getRound2QuestionData }

export async function submitRound2Answer(gameCode: string, data: { player_id: number; question_id: number; player_answer: string }) {
  return fetchApi<any>(`/round2/${gameCode}/answer`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}
export { submitRound2Answer as submitAnswerRound2 }

export async function getRound2Leaderboard(gameCode: string) {
  return fetchApi<any>(`/round2/${gameCode}/leaderboard`)
}
export { getRound2Leaderboard as getLeaderboard }

export async function advanceRound2Phase(gameCode: string) {
  return fetchApi<any>(`/round2/${gameCode}/advance`, {
    method: 'POST',
  })
}
export { advanceRound2Phase as advancePhase }

export async function getRound2Progress(gameCode: string) {
  return fetchApi<any>(`/round2/${gameCode}/progress`)
}
export { getRound2Progress as getProgress }

// === Ping-Pong ===

export async function getRandomPingPongTheme() {
  return fetchApi<any>('/ping-pong/random')
}

export async function submitPingPongAnswer(data: {
  game_session_id: number
  theme_id: number
  team_id: number
  answers_given: string[]
}) {
  return fetchApi<any>('/ping-pong/answer', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getPingPongResults(gameCode: string, themeId: number) {
  return fetchApi<any>(`/games/${gameCode}/ping-pong-results/${themeId}`)
}

// === Manche 3 (Grille Mémoire) ===

export async function createMemoryGrid(gameCode: string) {
  return fetchApi<any>(`/games/${gameCode}/memory-grid/create`, {
    method: 'POST',
  })
}

export async function startMemoryGridRound(gameCode: string) {
  return fetchApi<any>(`/games/${gameCode}/memory-grid/start`, {
    method: 'POST',
  })
}

export async function getMemoryGridState(gridId: number) {
  return fetchApi<any>(`/memory-grid/${gridId}/state`)
}

export async function revealCell(data: any) {
  return fetchApi<any>('/memory-grid/reveal-cell', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function answerCell(data: any) {
  return fetchApi<any>('/memory-grid/answer-cell', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}