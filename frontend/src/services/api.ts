import type {
  GameSession,
  QuestionResponse,
  AnswerResponse,
  WheelSpinResponse,
  MemoryGridState,
  MemoryGridCreateResponse,
  CreateGameRequest,
  CreateTeamRequest,
  SubmitAnswerRequest,
  UseTokenRequest,
  SelectCellRequest,
  AnswerCellRequest,
  AnswerCellResponse,
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
  return fetchApi<MemoryGridCreateResponse>(`/games/${code}/memory-grid/create`, {
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
  return fetchApi<AnswerCellResponse>('/memory-grid/answer-cell', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// AD-0 : les 4 finalistes de la Manche 3, classés par score de Manche 2.
export async function getMemoryGridFinalists(code: string) {
  return fetchApi<{ finalists: number[]; game_session_id: number }>(
    `/games/${code}/memory-grid/finalists`
  )
}

export interface MemoryGridStandings {
  is_completed: boolean
  player_scores: Array<{
    player_id: number
    player_name: string
    stolen_cells: number
    own_theme_cells: number
    unassigned_cells: number
    total_score: number
  }>
  winner: { player_id: number; player_name: string; total_score: number } | null
  is_tie: boolean
  message: string
}

// Classement final adressé par code de partie (AD-1 : Manche 3 seule).
export async function getFinalStandings(code: string) {
  return fetchApi<MemoryGridStandings>(`/games/${code}/memory-grid/standings`)
}

// Classement courant des finalistes (AD-1 : score de Manche 3 uniquement).
export async function getMemoryGridStandings(memoryGridId: number) {
  return fetchApi<{
    is_completed: boolean
    player_scores: Array<{
      player_id: number
      player_name: string
      stolen_cells: number
      own_theme_cells: number
      unassigned_cells: number
      total_score: number
    }>
    winner: { player_id: number; player_name: string; total_score: number } | null
    is_tie: boolean
    message: string
  }>(`/memory-grid/${memoryGridId}/winner`)
}

export async function getCurrentPlayerTurn(memoryGridId: number) {
  return fetchApi<{
    memory_grid_id: number
    current_turn: number
    finalists: number[]
    current_player_id: number | null
  }>(`/memory-grid/${memoryGridId}/current-player-turn`)
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

// === Ping-Pong Duel ===

export async function getRandomPingPongTheme() {
  return fetchApi<{
    id: number
    title: string
    description: string | null
    correct_answers: string[]
    min_answers_to_win: number
    created_at: string
  }>('/ping-pong/random-theme')
}

// === Multi-screen Team State ===

export async function getTeamState(gameCode: string, teamId: number) {
  return fetchApi<{
    team_id: number
    team_name: string
    team_score: number
    game_phase: string
    is_my_turn: boolean
    has_answered: boolean
    current_question: {
      id: number
      text: string
      category: string
      difficulty: string
      points: number
      correct_answer: string | null
      options: string[]
    } | null
    active_duel: {
      duel_id: number
      theme: {
        id: number
        title: string
        description: string | null
        correct_answers: string[]
        min_answers_to_win: number
      }
      team1: { id: number; name: string }
      team2: { id: number; name: string }
      current_turn_team_id: number
      current_turn_team_name: string
      turn_number: number
      answers_used: string[]
      is_completed: boolean
      winner_team_id: number | null
      is_my_turn_in_duel: boolean
    } | null
    tokens: { id: number; token_type: string; is_used: boolean }[]
    other_teams: { team_id: number; team_name: string; has_answered: boolean }[]
    all_answered: boolean
    validation_result: {
      correct_answer: string
      teams: { team_name: string; is_correct: boolean; points_earned: number }[]
    } | null
  }>(`/game/${gameCode}/team/${teamId}/state`)
}

export async function startPingPongDuel(data: {
  game_session_id: number
  theme_id: number
  team1_id: number
  team2_id: number
}) {
  return fetchApi<{
    duel_id: number
    theme: {
      id: number
      title: string
      description: string | null
      correct_answers: string[]
      min_answers_to_win: number
      created_at: string
    }
    team1: { id: number; name: string }
    team2: { id: number; name: string }
    current_turn_team_id: number
    turn_number: number
    answers_used: string[]
    is_completed: boolean
    winner_team_id: number | null
  }>('/ping-pong/duel/start', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function submitPingPongDuelAnswer(data: {
  duel_id: number
  team_id: number
  answer: string
}) {
  return fetchApi<{
    is_correct: boolean
    answer: string
    turn_number: number
    duel_continues: boolean
    winner_team_id: number | null
    winner_team_name: string | null
    next_turn_team_id: number | null
    message: string
  }>('/ping-pong/duel/answer', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getPingPongDuelState(duelId: number) {
  return fetchApi<{
    duel_id: number
    theme: {
      id: number
      title: string
      description: string | null
      correct_answers: string[]
      min_answers_to_win: number
    }
    team1: { id: number; name: string }
    team2: { id: number; name: string }
    current_turn_team_id: number
    current_turn_team_name: string
    turn_number: number
    answers_used: string[]
    is_completed: boolean
    winner_team_id: number | null
  }>(`/ping-pong/duel/${duelId}`)
}

export async function registerHost(gameCode: string) {
  return fetchApi<{ message: string; has_host: boolean }>(`/games/${gameCode}/register-host`, {
    method: 'POST',
  })
}

export async function nextQuestion(gameCode: string) {
  return fetchApi<{ message: string; question_id: number; question_text: string }>(`/games/${gameCode}/next-question`, {
    method: 'POST',
  })
}

export async function getPingPongDuelResults(duelId: number) {
  return fetchApi<{
    duel_id: number
    theme: {
      id: number
      title: string
      description: string | null
      correct_answers: string[]
      min_answers_to_win: number
    }
    team1: {
      id: number
      name: string
      turns: number
      correct_answers: string[]
    }
    team2: {
      id: number
      name: string
      turns: number
      correct_answers: string[]
    }
    winner_team_id: number
    winner_team_name: string
    total_turns: number
    answers_used: string[]
  }>(`/ping-pong/duel/${duelId}/results`)
}
