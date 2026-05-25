import type {
  GameSession,
  QuestionResponse,
  AnswerResponse,
  WheelSpinResponse,
  MemoryGridState,
  CreateGameRequest,
  CreateTeamRequest,
  SubmitAnswerRequest,
  UseTokenRequest,
  SelectCellRequest,
  AnswerCellRequest,
  Team,
} from '../types'

const API_BASE = '/api'

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

export async function createGame(data: CreateGameRequest) {
  return fetchApi<{ game: GameSession; message: string }>('/games/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getGame(code: string) {
  return fetchApi<GameSession>(`/games/${code}`)
}

export async function startGame(code: string) {
  return fetchApi<{ message: string; teams: number }>(`/games/${code}/start`, {
    method: 'POST',
  })
}

export async function advanceToPhase3(code: string) {
  return fetchApi<{ message: string; current_round: string }>(`/games/${code}/advance-to-phase3`, {
    method: 'POST',
  })
}

// === Équipes ===

export async function createTeam(code: string, data: CreateTeamRequest) {
  return fetchApi<Team>(`/games/${code}/teams/`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// === Questions ===

export async function getRandomQuestion(category?: string, difficulty?: string) {
  const params = new URLSearchParams()
  if (category) params.set('category', category)
  if (difficulty) params.set('difficulty', difficulty)
  const query = params.toString() ? `?${params.toString()}` : ''
  return fetchApi<QuestionResponse>(`/questions/random${query}`)
}

export async function getCurrentQuestion(gameCode: string) {
  return fetchApi<QuestionResponse>(`/games/${gameCode}/current-question`)
}

export async function setCurrentQuestion(gameCode: string, questionId: number) {
  return fetchApi<{ message: string; question: string; question_id: number }>(`/games/${gameCode}/set-current-question`, {
    method: 'POST',
    body: JSON.stringify({ question_id: questionId }),
  })
}

export async function getAnswersStatus(gameCode: string, questionId?: number) {
  const query = questionId ? `?question_id=${questionId}` : ''
  return fetchApi<{
    question_id: number | null;
    total_teams: number;
    answered_teams: number[];
    remaining_teams: number[];
    all_answered: boolean;
  }>(`/games/${gameCode}/answers-status${query}`)
}

export async function getTeamTokens(teamId: number) {
  return fetchApi<{ tokens: { id: number; token_type: string; is_used: boolean }[] }>(`/teams/${teamId}/tokens`)
}

// === Réponses ===

export async function submitAnswer(data: SubmitAnswerRequest) {
  return fetchApi<AnswerResponse>('/answers/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// === Jetons ===

export async function useToken(data: UseTokenRequest) {
  return fetchApi<{ message: string; effect: string; token_id: number }>('/tokens/use', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// === Roue ===

export async function spinWheel(teamId: number) {
  return fetchApi<WheelSpinResponse>('/wheel/spin', {
    method: 'POST',
    body: JSON.stringify({ team_id: teamId }),
  })
}

// === Grille Mémoire ===

export async function createMemoryGrid(code: string) {
  return fetchApi<MemoryGridState>(`/games/${code}/memory-grid/create`, {
    method: 'POST',
  })
}

export async function startMemoryGridRound(code: string) {
  return fetchApi<{ round_id: number; message: string }>(`/games/${code}/memory-grid/start`, {
    method: 'POST',
  })
}

export async function getMemoryGridState(memoryGridId: number) {
  return fetchApi<MemoryGridState>(`/memory-grid/${memoryGridId}/state`)
}

export async function revealCell(data: SelectCellRequest) {
  return fetchApi<{ status: string; cell: unknown }>('/memory-grid/reveal-cell', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function answerCell(data: AnswerCellRequest) {
  return fetchApi<{ status: string; is_correct: boolean; points_awarded: number }>('/memory-grid/answer-cell', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// === Round 2 (16→8→4 Tournament) ===

import type {
  Theme,
  ThemeSelectionRequest,
  ThemeSelectionResponse,
  Round2QuestionResponse,
  Round2AnswerRequest,
  Round2AnswerResponse,
  TournamentProgress,
  IntermediateLeaderboardResponse,
  Round2AdvanceResponse,
} from '../types'

export async function getRound2Themes(gameCode: string) {
  return fetchApi<{ themes: Theme[]; game_session_id: number }>(`/round2/${gameCode}/themes`)
}

export async function selectTheme(gameCode: string, data: ThemeSelectionRequest) {
  return fetchApi<ThemeSelectionResponse>(`/round2/${gameCode}/select-theme`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getRound2Question(gameCode: string, playerId: number) {
  return fetchApi<Round2QuestionResponse>(`/round2/${gameCode}/question?player_id=${playerId}`)
}

export async function submitRound2Answer(gameCode: string, data: Round2AnswerRequest) {
  return fetchApi<Round2AnswerResponse>(`/round2/${gameCode}/answer`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getRound2Leaderboard(gameCode: string) {
  return fetchApi<IntermediateLeaderboardResponse>(`/round2/${gameCode}/leaderboard`)
}

export async function advanceRound2Phase(gameCode: string) {
  return fetchApi<Round2AdvanceResponse>(`/round2/${gameCode}/advance`, {
    method: 'POST',
  })
}

export async function getRound2Progress(gameCode: string) {
  return fetchApi<TournamentProgress>(`/round2/${gameCode}/progress`)
}

// === Ping-Pong ===

export async function getRandomPingPongTheme() {
  return fetchApi<{
    id: number
    title: string
    description: string | null
    correct_answers: string[]
    min_answers_to_win: number
    created_at: string
  }>('/ping-pong/random')
}

export async function submitPingPongAnswer(data: {
  game_session_id: number
  theme_id: number
  team_id: number
  answers_given: string[]
}) {
  return fetchApi<{
    correct_count: number
    total_possible: number
    points_earned: number
    correct_answers_given: string[]
    missed_answers: string[]
    team_score: number
    is_winner: boolean
  }>('/ping-pong/answer', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getPingPongResults(gameCode: string, themeId: number) {
  return fetchApi<{
    theme: {
      id: number
      title: string
      description: string | null
      correct_answers: string[]
      min_answers_to_win: number
    }
    team_results: Array<{
      team_id: number
      team_name: string
      correct_count: number
      points: number
      answers: string[]
    }>
    winner_team_id: number | null
    all_teams_answered: boolean
  }>(`/games/${gameCode}/ping-pong-results/${themeId}`)
}
