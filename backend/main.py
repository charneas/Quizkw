import logging
import os
import random  # noqa: F401 -- monkeypatché par les tests via `main.random.randint`
# (test_wheel_auto_trigger.py, test_wheel_spin_persistence.py) ; le module
# `random` étant partagé (sys.modules), patcher main.random affecte aussi
# app/manche1_orchestration.py qui fait le vrai tirage. main.py lui-même
# n'appelle plus random directement depuis H.019.
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.database import engine
from app.models import Base
from app.rate_limit import limiter
from main_extended import router
from main_admin import router as admin_router, auth_router as admin_auth_router
from main_content_gen import router as content_gen_router, player_router as content_flag_router
from main_propositions import router as propositions_router
from main_games import router as games_router
from main_teams import router as teams_router, PENALTY_POINTS
from main_manche1 import router as manche1_router
from main_round2 import router as round2_router
from main_ping_pong import router as ping_pong_router
from main_memory_grid_legacy import router as memory_grid_router

# E-002 : journalisation minimale au niveau module (voir la spine § Deferred —
# pas d'infrastructure d'observabilité, seulement logging.getLogger standard
# aux points de transition de phase et d'erreur).
# basicConfig est nécessaire : sans configuration explicite, le logger racine
# reste au niveau WARNING par défaut et les logger.info() ajoutés seraient
# silencieusement ignorés (trouvé en revue de code — l'objectif même de
# diagnosticabilité de cette story aurait été vide de sens sans ça).
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Quizkw API",
    description="API pour le jeu de quiz Quizkw avec règles complexes",
    version="1.0.0"
)

# Rate limiting (revue de sécurité, 2026-08-15) : aucune protection n'existait
# auparavant, combiné aux actions non authentifiées trouvées lors du même
# audit (roue, réponses...) cela permettait un DoS/triche par spam trivial.
# default_limits s'applique à toutes les routes sans changement de code ;
# certains endpoints à fort enjeu (roue, réponses, jetons) ont en plus une
# limite plus stricte via @limiter.limit (voir leurs routers).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS : en dev (Vite, vite.config.ts) comme en prod (Nginx, DEPLOY.md §6),
# le frontend appelle l'API via un proxy same-origin sous /api/ — aucune
# requête cross-origin n'est légitimement nécessaire. `allow_origins=["*"]`
# combiné à `allow_credentials=True` était donc à la fois inutile et
# dangereux (n'importe quel site tiers pouvait faire des requêtes
# authentifiées par cookie admin_session). CORS_ALLOWED_ORIGINS permet
# d'ajouter explicitement une origine (ex. un frontend hébergé séparément)
# si un besoin cross-origin réel apparaît.
_cors_allowed_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.responses import JSONResponse
from fastapi import Request


# Include extended endpoints for Memory Grid Round 3
app.include_router(router)
# Include admin login/logout (Epic F-ext-2, story F-ext-2.1) — mounted before
# the guarded admin router, unauthenticated by design (obtaining the cookie)
app.include_router(admin_auth_router)
# Include admin endpoints for content management (Epic F) — guarded since F-ext-2.1 (AD-17)
app.include_router(admin_router)
# Include content generation (F.2) and player flagging endpoints (Epic F)
app.include_router(content_gen_router)
app.include_router(content_flag_router)
# Include public proposition submission endpoint (Epic F-ext, story F-ext-1.1)
app.include_router(propositions_router)
# Include session/host lifecycle endpoints (Epic H, story H.014)
app.include_router(games_router)
# Include teams/players/tokens endpoints (Epic H, story H.015)
app.include_router(teams_router)
# Include questions/wheel/validation endpoints (Epic H, story H.016)
app.include_router(manche1_router)
# Include tournament round 2 endpoints (Epic H, story H.017)
app.include_router(round2_router)
# Include ping-pong duel endpoints (Epic H, story H.018)
app.include_router(ping_pong_router)
# Include memory grid (Manche 3) endpoints (Epic H, story H.019)
app.include_router(memory_grid_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)