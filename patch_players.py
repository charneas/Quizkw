from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sys
import os

# Ensure the backend directory is in the path
sys.path.append(os.path.abspath('./backend'))

from app import models
from app.database import engine

# Connect to the database
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

# Get all teams
teams = db.query(models.Team).all()
game = db.query(models.GameSession).filter(models.GameSession.id == (teams[0].game_session_id if teams else None)).first()

if not teams or not game:
    print("Error: Create teams in the lobby first.")
    sys.exit(1)

players_per_team = game.players_per_team
total_needed = len(teams) * players_per_team

# Create enough players
current_players = db.query(models.Player).all()
players_to_create = total_needed - len(current_players)

if players_to_create > 0:
    print(f"Creating {players_to_create} dummy players...")
    for i in range(players_to_create):
        new_player = models.Player(name=f"Player {len(current_players) + i + 1}", team_id=None)
        db.add(new_player)
    db.commit()

# Assign players to teams
players = db.query(models.Player).filter(models.Player.team_id == None).all()
print(f"Assigning {len(players)} players to teams...")

player_idx = 0
for team in teams:
    for _ in range(players_per_team):
        if player_idx < len(players):
            players[player_idx].team_id = team.id
            player_idx += 1

db.commit()
db.close()
print("Success! Teams are populated. Refresh Lobby.")
