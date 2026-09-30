#!/usr/bin/env node
/**
 * Captures d'écran de démo pour le carrousel de la Home
 * (_bmad-output/spec-home-demo-carousel.md).
 *
 * Joue une partie FICTIVE sur une stack LOCALE et écrit 8 images WebP
 * (≤ 150 Ko chacune) dans frontend/public/demo/ :
 *   {question,wheel,blindtest,podium}-{mobile,desktop}.webp
 *   mobile : viewport 390×844 @2x — desktop : 1280×800 @1x (viewport seul).
 *
 * Ne démarre RIEN : le backend et le frontend doivent déjà tourner, sur des
 * DB jetables (jamais backend/quizkw.db, jamais la prod).
 *
 * Usage (PowerShell, depuis la racine du repo) :
 *   1. Backend, depuis backend/ :
 *        $env:DATABASE_URL = "sqlite:///C:/chemin/scratch/quizkw-demo.db"
 *        $env:BLINDTEST_DATABASE_URL = "sqlite:///C:/chemin/scratch/blindtest-demo.db"
 *        $env:SESSION_SECRET_KEY = "demo"; $env:RATE_LIMIT_ENABLED = "false"
 *        $env:DISCORD_CLIENT_ID = "x"; $env:DISCORD_CLIENT_SECRET = "x"
 *        $env:DISCORD_REDIRECT_URI = "http://localhost/x"; $env:DISCORD_SESSION_SECRET_KEY = "x"
 *        .\venv\Scripts\python.exe -m uvicorn main:app --port 8000
 *      puis, UNE fois le backend démarré (il crée le schéma), avec les mêmes
 *      variables : $env:PYTHONIOENCODING = "utf-8"; .\venv\Scripts\python.exe seed.py
 *      (seed.py VIDE la DB pointée par DATABASE_URL.)
 *   2. Frontend, depuis frontend/ : npx vite --port 3000
 *   3. Depuis frontend/ :
 *        $env:DEMO_BLINDTEST_DB = "C:/chemin/scratch/blindtest-demo.db"
 *        node scripts/capture-demo.mjs
 *
 * Variables :
 *   DEMO_BASE_URL      URL du frontend vite (défaut http://localhost:3000) ;
 *                      l'API est jointe via son proxy /api. Refusé si l'hôte
 *                      n'est pas local.
 *   DEMO_BLINDTEST_DB  (obligatoire) fichier SQLite blindtest du backend local.
 *                      Les morceaux du blindtest y sont insérés directement :
 *                      l'import de playlist passe par YouTube/Deezer, ce qu'une
 *                      démo ne doit pas dépendre. Refusé s'il s'agit de
 *                      backend/blindtest.db du repo.
 *
 * Seule donnée simulée : le classement de Manche 3 sur /results (route
 * /games/{code}/memory-grid/standings interceptée par Playwright), l'atteindre
 * pour de vrai demandant une partie complète en 3 manches. Tout le reste
 * (équipes, scores, question, roue, rounds de blindtest) est joué via l'API.
 * Requiert Node ≥ 22.13 (node:sqlite) et Chromium Playwright installé.
 * Durée : ~2 min (les rounds de blindtest durent 20 s + 6 s de reveal).
 */
import { chromium } from '@playwright/test'
import { DatabaseSync } from 'node:sqlite'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = resolve(HERE, '../public/demo')
const REPO_BLINDTEST_DB = resolve(HERE, '../../backend/blindtest.db')
const MAX_BYTES = 150 * 1024

const BASE_URL = (process.env.DEMO_BASE_URL || 'http://localhost:3000').replace(/\/$/, '')
const API = `${BASE_URL}/api`
const BLINDTEST_DB = process.env.DEMO_BLINDTEST_DB

const VIEWPORTS = {
  mobile: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
  desktop: { viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 },
}

// --- Garde-fous -------------------------------------------------------------

function assertSafeTarget() {
  const host = new URL(BASE_URL).hostname
  if (!['localhost', '127.0.0.1', '[::1]', '::1'].includes(host)) {
    throw new Error(`DEMO_BASE_URL doit pointer vers une stack locale (reçu : ${BASE_URL})`)
  }
  if (!BLINDTEST_DB) {
    throw new Error('DEMO_BLINDTEST_DB est requis (fichier SQLite blindtest jetable du backend local)')
  }
  if (resolve(BLINDTEST_DB).toLowerCase() === REPO_BLINDTEST_DB.toLowerCase()) {
    throw new Error('DEMO_BLINDTEST_DB ne doit pas être backend/blindtest.db du repo : utiliser une DB jetable')
  }
}

// --- Données fictives -------------------------------------------------------

const TEAMS = [
  { key: 'A', name: 'Les Cerveaux Lents', icon: '🐢', players: ['Camille', 'Antoine'] },
  { key: 'B', name: 'Quiz de Lyon', icon: '🦁', players: ['Mehdi', 'Julie'] },
  { key: 'C', name: 'Team Raclette', icon: '🧀', players: ['Léa', 'Hugo'] },
  { key: 'D', name: 'Les Boulets de Canon', icon: '💣', players: ['Inès', 'Thomas'] },
]
// L'équipe dont on montre le téléphone (2e au classement au moment de la capture).
const VIEWER_TEAM = 'C'

// Questions déjà jouées avant la capture (textes issus de backend/seed.py) et
// équipes qui y répondent juste : A=10, C=6, B=4, D=2 points.
const PLAYED_ROUNDS = [
  { match: 'capitale de la France', correct: ['A', 'B', 'D'] },
  { match: 'Joconde', correct: ['A', 'B'] },
  { match: 'Zarathoustra', correct: ['A', 'C'] },
]
// Question affichée sur le téléphone : A et D ont déjà répondu, pas B.
const SHOWCASE = { match: 'plus grand océan', answered: { A: 'correct', D: 'wrong' } }

const BLINDTEST_PLAYERS = {
  // Ordre de connexion : le premier devient l'hôte (bot).
  bots: ['Mehdi', 'Chloé'],
  pages: { mobile: 'Léa', desktop: 'Hugo' },
}
const BLINDTEST_TRACKS = {
  Mehdi: [['Alors on danse', 'Stromae'], ['Djadja', 'Aya Nakamura'], ['Bella', 'Maître Gims']],
  Chloé: [['Dernière danse', 'Indila'], ['Tout oublier', 'Angèle'], ['La Grenade', 'Clara Luciani']],
  Léa: [['Voyage voyage', 'Desireless'], ['Je veux', 'Zaz'], ['Le Sud', 'Nino Ferrer']],
  Hugo: [['Get Lucky', 'Daft Punk'], ['Mistral gagnant', 'Renaud'], ['Formidable', 'Stromae']],
}

// --- Utilitaires ------------------------------------------------------------

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function api(method, path, body, headers = {}) {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { 'content-type': 'application/json', ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await res.text()
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status} ${text}`)
  return text ? JSON.parse(text) : null
}

async function newContext(browser, kind, extraStorage = {}) {
  const context = await browser.newContext({
    ...VIEWPORTS[kind],
    colorScheme: 'dark',
    reducedMotion: 'reduce',
    locale: 'fr-FR',
  })
  // Jamais de pageview vers les stats de prod, pas de widget de don, pas de
  // lecteur YouTube (son + réseau) pendant la capture.
  await context.route(/stats\.quizclimb\.fr|ko-fi\.com|youtube\.com|ytimg\.com|googlevideo\.com/, (route) =>
    route.abort(),
  )
  await context.addInitScript((storage) => {
    try {
      localStorage.setItem('quizkw_theme', 'dark')
      for (const [k, v] of Object.entries(storage)) localStorage.setItem(k, v)
    } catch {
      /* stockage indisponible : thème par défaut (sombre) */
    }
  }, extraStorage)
  return context
}

/** Échoue si la page montre un chargement, une erreur ou un badge dev. */
async function assertCleanPage(page, label) {
  const forbidden = [
    'DEV: Fast Track',
    'Connexion à la partie',
    'Chargement...',
    'Erreur',
    'Partie non trouvée',
    'Équipe non trouvée',
    'Connexion perdue',
  ]
  for (const text of forbidden) {
    if (await page.getByText(text).first().isVisible().catch(() => false)) {
      throw new Error(`${label} : texte interdit visible à l'écran ("${text}")`)
    }
  }
}

let encoderPage = null

/** PNG -> WebP via l'encodeur canvas de Chromium (aucune dépendance), en
 * baissant la qualité jusqu'à passer sous MAX_BYTES. */
async function toWebp(png) {
  const b64 = png.toString('base64')
  for (let quality = 0.9; quality >= 0.3; quality -= 0.05) {
    const dataUrl = await encoderPage.evaluate(
      async ({ b64, quality }) => {
        const img = new Image()
        img.src = `data:image/png;base64,${b64}`
        await img.decode()
        const canvas = document.createElement('canvas')
        canvas.width = img.naturalWidth
        canvas.height = img.naturalHeight
        canvas.getContext('2d').drawImage(img, 0, 0)
        return canvas.toDataURL('image/webp', quality)
      },
      { b64, quality },
    )
    const buf = Buffer.from(dataUrl.split(',')[1], 'base64')
    if (buf.length <= MAX_BYTES) return { buf, quality }
  }
  throw new Error('Impossible de descendre sous 150 Ko en WebP')
}

async function capture(page, name, kind) {
  await assertCleanPage(page, `${name}-${kind}`)
  // Laisse polices et transitions se stabiliser.
  await page.evaluate(() => document.fonts.ready)
  await sleep(400)
  const png = await page.screenshot({ type: 'png', fullPage: false })
  const { buf, quality } = await toWebp(png)
  const file = resolve(OUT_DIR, `${name}-${kind}.webp`)
  writeFileSync(file, buf)
  console.log(`  ✔ ${name}-${kind}.webp  ${(buf.length / 1024).toFixed(1)} Ko (q=${quality.toFixed(2)})`)
}

// --- Quiz : question, roue, podium -----------------------------------------

async function setupQuizGame() {
  const created = await api('POST', '/games/', {
    total_players: 8,
    players_per_team: 2,
    manche1_question_count: 50,
    wheel_frequency: 5,
  })
  const code = created.game.code
  const hostHeaders = { 'X-Host-Token': created.host_token }

  const teams = {}
  for (const t of TEAMS) {
    const team = await api('POST', `/games/${code}/teams/`, { name: t.name, icon: t.icon })
    const players = []
    for (const name of t.players) {
      const p = await api('POST', `/games/${code}/teams/${team.id}/players/`, { name })
      players.push({ id: p.id, name: p.name })
    }
    teams[t.key] = { ...t, id: team.id, token: team.team_token, players }
  }
  await api('POST', `/games/${code}/start`, undefined, hostHeaders)

  // Catalogue des questions de Manche 1 (sans thème) : set-current-question +
  // current-question donnent texte, options et bonne réponse.
  const catalogue = []
  for (let id = 1; id <= 40; id++) {
    try {
      await api('POST', `/games/${code}/set-current-question`, { question_id: id }, hostHeaders)
      const cq = await api('GET', `/games/${code}/current-question`)
      if (!cq.question.theme_id && !cq.question.image_url) catalogue.push({ ...cq.question, options: cq.options })
    } catch {
      /* id absent : ignoré */
    }
  }
  const pick = (match) => {
    const q = catalogue.find((c) => c.text.includes(match))
    if (!q) throw new Error(`Question "${match}" introuvable dans la DB (lancer backend/seed.py)`)
    return q
  }

  const answer = (team, q, correct) =>
    api(
      'POST',
      '/answers/',
      {
        question_id: q.id,
        team_id: team.id,
        player_answer: correct ? q.correct_answer : q.options.find((o) => o !== q.correct_answer),
      },
      { 'X-Team-Token': team.token },
    )

  // Chaque question passe par next-question (compteur de tours réel, qui
  // déclenche la roue tous les `wheel_frequency` tours), puis est remplacée
  // par la question choisie.
  const playQuestion = async (q) => {
    const res = await api('POST', `/games/${code}/next-question`, undefined, hostHeaders)
    if (!res.question_id) throw new Error(`next-question inattendu : ${JSON.stringify(res)}`)
    await api('POST', `/games/${code}/set-current-question`, { question_id: q.id }, hostHeaders)
  }

  for (const round of PLAYED_ROUNDS) {
    const q = pick(round.match)
    await playQuestion(q)
    for (const t of Object.values(teams)) await answer(t, q, round.correct.includes(t.key))
    await api('POST', `/games/${code}/validate-answers`, undefined, hostHeaders)
  }

  return { code, hostHeaders, teams, pick, answer, playQuestion }
}

async function openTeamPage(context, game, teamKey) {
  const page = await context.newPage()
  await page.goto(`${BASE_URL}/team/${game.code}/${game.teams[teamKey].id}`)
  await page.getByText('Classement').first().waitFor({ timeout: 15000 })
  return page
}

async function captureQuiz(browser) {
  console.log('Quiz : préparation de la partie…')
  const game = await setupQuizGame()
  const storage = Object.fromEntries(
    Object.values(game.teams).map((t) => [`quizkw_team_token_${t.id}`, t.token]),
  )
  const contexts = {
    mobile: await newContext(browser, 'mobile', storage),
    desktop: await newContext(browser, 'desktop', storage),
  }

  // 1) Question en cours sur le téléphone de l'équipe VIEWER_TEAM.
  const q = game.pick(SHOWCASE.match)
  await game.playQuestion(q)
  for (const [key, verdict] of Object.entries(SHOWCASE.answered)) {
    await game.answer(game.teams[key], q, verdict === 'correct')
  }
  const viewerPages = {}
  for (const kind of Object.keys(contexts)) {
    const page = await openTeamPage(contexts[kind], game, VIEWER_TEAM)
    await page.getByText(q.text).waitFor({ timeout: 15000 })
    await page.getByRole('button', { name: q.correct_answer, exact: true }).click()
    if (kind === 'mobile') {
      // Sur mobile le classement passe au-dessus : on cadre sur la question,
      // pastilles "a répondu" tout en haut (le bouton de thème, fixe, reste
      // à droite de la première ligne de pastilles).
      await page.getByText(q.text).evaluate((el) => {
        const chips = el.closest('.card').previousElementSibling
        window.scrollTo(0, chips.getBoundingClientRect().top + window.scrollY - 16)
      })
    }
    await capture(page, 'question', kind)
    viewerPages[kind] = page
  }
  await game.answer(game.teams[VIEWER_TEAM], q, true)
  await api('POST', `/games/${game.code}/validate-answers`, undefined, game.hostHeaders)

  // 2) Roue de fortune : tirage aléatoire par équipe. Toutes les pages
  //    d'équipe doivent être ouvertes AVANT le tirage (le popup ne s'affiche
  //    que pour un événement postérieur au premier chargement), puis on
  //    capture l'équipe qui a tiré l'effet le plus parlant.
  for (const p of Object.values(viewerPages)) await p.close()
  let wheelDone = false
  for (let attempt = 1; attempt <= 8 && !wheelDone; attempt++) {
    const pages = { mobile: {}, desktop: {} }
    for (const kind of Object.keys(contexts)) {
      for (const key of Object.keys(game.teams)) pages[kind][key] = await openTeamPage(contexts[kind], game, key)
    }
    await sleep(2500) // au moins un poll de référence par page
    // Une page (ré)ouverte peut rejouer le dernier effet déjà tiré (popup ou
    // choix d'adversaire ping-pong d'un tirage précédent) : on les referme
    // pour que seul le nouveau tirage soit visible à l'écran.
    for (const kind of Object.keys(pages)) {
      for (const page of Object.values(pages[kind])) {
        const cancel = page.getByRole('button', { name: /Annuler le duel/ })
        if (await cancel.isVisible().catch(() => false)) await cancel.click()
        const cont = page.getByRole('button', { name: /Continuer/ })
        if (await cont.isVisible().catch(() => false)) await cont.click()
      }
    }

    let events = null
    for (let i = 0; i < 5 && !events; i++) {
      const res = await api('POST', `/games/${game.code}/next-question`, undefined, game.hostHeaders)
      if (res.wheel_events) events = res.wheel_events
    }
    if (!events) throw new Error('La roue ne s’est pas déclenchée')

    // Accueil : on ne montre qu'un bonus (décision owner 2026-09-30), le +3
    // de préférence. Malus et ping-pong -> on relance la roue.
    const rank = (e) => (e.effect_type !== 'bonus' ? 0 : e.value === 3 ? 2 : 1)
    const best = [...events].sort((a, b) => rank(b) - rank(a))[0]
    if (rank(best) > 0) {
      const key = Object.values(game.teams).find((t) => t.id === best.target_team_id).key
      for (const kind of Object.keys(contexts)) {
        const page = pages[kind][key]
        await page.getByRole('button', { name: /Continuer/ }).waitFor({ timeout: 15000 })
        await capture(page, 'wheel', kind)
      }
      wheelDone = true
    } else {
      console.log(`  (tirage ${attempt} : aucun bonus, on relance)`)
    }
    for (const kind of Object.keys(pages)) for (const p of Object.values(pages[kind])) await p.close()
  }
  if (!wheelDone) throw new Error('Aucun bonus de roue après 8 tirages')

  // 3) Podium final. Le classement de Manche 3 est simulé (voir en-tête) :
  //    joueurs réels de la partie, scores cohérents (1 à 3 pts par case,
  //    16 cases).
  const pl = (key, i) => game.teams[key].players[i]
  const podium = [
    { p: pl('A', 0), own: 5, stolen: 2, score: 15 },
    { p: pl('C', 0), own: 3, stolen: 2, score: 11 },
    { p: pl('B', 0), own: 2, stolen: 0, score: 5 },
    { p: pl('D', 1), own: 2, stolen: 0, score: 3 },
  ]
  const standings = {
    is_completed: true,
    player_scores: podium.map(({ p, own, stolen, score }) => ({
      player_id: p.id,
      player_name: p.name,
      stolen_cells: stolen,
      own_theme_cells: own,
      unassigned_cells: 0,
      total_score: score,
    })),
    winner: { player_id: podium[0].p.id, player_name: podium[0].p.name, total_score: podium[0].score },
    is_tie: false,
    message: `${podium[0].p.name} remporte la partie !`,
  }
  for (const kind of Object.keys(contexts)) {
    const page = await contexts[kind].newPage()
    await page.route('**/api/games/*/memory-grid/standings', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(standings) }),
    )
    await page.goto(`${BASE_URL}/results/${game.code}`)
    await page.getByText(podium[0].p.name).waitFor({ timeout: 15000 })
    await capture(page, 'podium', kind)
    await page.close()
  }

  for (const c of Object.values(contexts)) await c.close()
}

// --- Blindtest --------------------------------------------------------------

function wsUrl(code) {
  const u = new URL(`${API}/blindtest/games/${code}/ws`)
  u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'
  return u.toString()
}

function connectBot(code, pseudo, onMessage) {
  return new Promise((resolveBot, reject) => {
    const ws = new WebSocket(wsUrl(code))
    const send = (type, payload) => ws.send(JSON.stringify({ type, payload }))
    ws.onopen = () => send('join', { pseudo })
    ws.onerror = (e) => reject(new Error(`WS ${pseudo} : ${e.message || 'erreur'}`))
    let joined = false
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (!joined && msg.type === 'game_state') {
        joined = true
        resolveBot({ ws, send })
      }
      onMessage?.(msg)
    }
  })
}

function seedBlindtestTracks(gameId) {
  const db = new DatabaseSync(BLINDTEST_DB)
  const owners = new Map() // track id -> pseudo propriétaire
  try {
    const now = new Date().toISOString().replace('T', ' ').replace('Z', '')
    const insPlaylist = db.prepare(
      'INSERT INTO playlists (source_url, provider, created_at, game_id, owner_pseudo) VALUES (?, ?, ?, ?, ?)',
    )
    const insTrack = db.prepare(
      'INSERT INTO tracks (playlist_id, title, artist, youtube_video_id, duration_seconds, created_at) VALUES (?, ?, ?, ?, ?, ?)',
    )
    let n = 0
    for (const [pseudo, tracks] of Object.entries(BLINDTEST_TRACKS)) {
      const pl = insPlaylist.run(`https://www.youtube.com/playlist?list=DEMO${n}`, 'youtube', now, gameId, pseudo)
      for (const [title, artist] of tracks) {
        n++
        const videoId = `demoTrack${String(n).padStart(2, '0')}`
        const tr = insTrack.run(Number(pl.lastInsertRowid), title, artist, videoId, 200 + n, now)
        owners.set(Number(tr.lastInsertRowid), pseudo)
      }
    }
  } finally {
    db.close()
  }
  return owners
}

async function captureBlindtest(browser) {
  console.log('Blindtest : préparation de la partie…')
  const game = await api('POST', '/blindtest/games')
  const code = game.code

  const rounds = [] // { trackId, title } par round_started reçu
  let waiters = []
  const onBotMessage = (msg) => {
    if (msg.type === 'round_started') {
      rounds.push({ trackId: msg.payload.trackId, title: msg.payload.title })
      waiters.forEach((w) => w())
      waiters = []
    }
  }
  const waitRound = async (n) => {
    const deadline = Date.now() + 60000
    while (rounds.length < n) {
      if (Date.now() > deadline) throw new Error(`Round ${n} jamais démarré`)
      await new Promise((r) => {
        waiters.push(r)
        setTimeout(r, 1000)
      })
    }
    return rounds[n - 1]
  }

  const [hostName, otherBot] = BLINDTEST_PLAYERS.bots
  const host = await connectBot(code, hostName, onBotMessage)
  const bot2 = await connectBot(code, otherBot)

  const contexts = {}
  const pages = {}
  for (const [kind, pseudo] of Object.entries(BLINDTEST_PLAYERS.pages)) {
    contexts[kind] = await newContext(browser, kind)
    const page = await contexts[kind].newPage()
    await page.goto(`${BASE_URL}/blindtest/${code}`)
    await page.getByPlaceholder('Ton pseudo').fill(pseudo)
    await page.getByRole('button', { name: 'Rejoindre' }).click()
    await page.getByText('Joueurs présents').waitFor({ timeout: 15000 })
    pages[kind] = page
  }
  for (const page of Object.values(pages)) {
    await page.locator('li', { hasText: BLINDTEST_PLAYERS.pages.desktop }).first().waitFor()
  }

  const owners = seedBlindtestTracks(game.id)
  const everyone = [hostName, otherBot, ...Object.values(BLINDTEST_PLAYERS.pages)]
  const wrongFor = (guesser, owner) => everyone.find((p) => p !== guesser && p !== owner)

  // Qui devine juste à chaque round joué avant la capture (scores variés).
  const plan = [
    { Mehdi: false, Chloé: true, Léa: true, Hugo: true },
    { Mehdi: true, Chloé: false, Léa: true, Hugo: false },
  ]

  host.send('start_game', { rounds: 10 })
  for (let r = 1; r <= plan.length; r++) {
    const { trackId } = await waitRound(r)
    const owner = owners.get(trackId)
    const guessOf = (p) => (plan[r - 1][p] ? owner : wrongFor(p, owner))
    host.send('guess_submitted', { track_id: trackId, target_player_ids: [guessOf(hostName)] })
    bot2.send('guess_submitted', { track_id: trackId, target_player_ids: [guessOf(otherBot)] })
    for (const [kind, pseudo] of Object.entries(BLINDTEST_PLAYERS.pages)) {
      const page = pages[kind]
      await page.getByText('Qui a ajouté ce morceau').waitFor({ timeout: 15000 })
      if (pseudo === owner) continue
      await page.getByRole('button', { name: guessOf(pseudo), exact: true }).click()
      await page.getByRole('button', { name: 'Valider ma réponse' }).click()
    }
    console.log(`  round ${r} joué (morceau de ${owner}), attente du reveal…`)
  }

  const { trackId, title } = await waitRound(plan.length + 1)
  const owner = owners.get(trackId)
  for (const [kind, pseudo] of Object.entries(BLINDTEST_PLAYERS.pages)) {
    const page = pages[kind]
    await page.getByText(title).waitFor({ timeout: 15000 })
    // Un choix en cours (pas encore validé) pour montrer la sélection.
    const pickName = everyone.find((p) => p !== pseudo && p !== owner)
    await page.getByRole('button', { name: pickName, exact: true }).click()
    await capture(page, 'blindtest', kind)
  }

  host.ws.close()
  bot2.ws.close()
  for (const c of Object.values(contexts)) await c.close()
}

// --- Main -------------------------------------------------------------------

async function main() {
  assertSafeTarget()
  await api('GET', '/health')
  mkdirSync(OUT_DIR, { recursive: true })

  const browser = await chromium.launch()
  try {
    const encCtx = await browser.newContext()
    encoderPage = await encCtx.newPage()
    await captureQuiz(browser)
    await captureBlindtest(browser)
  } finally {
    await browser.close()
  }
  console.log(`Terminé : 8 images dans ${OUT_DIR}`)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
