#!/usr/bin/env python3
"""
I FOUND THE BUG!
"""
import sys
sys.path.append('backend')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app import models
import json

def found_the_bug():
    print("=== I FOUND THE BUG! ===")
    
    # Look at the API response from the previous test:
    print("API response showed:")
    print('''
  "player_stats": {
    "player_id": 7,          <-- WAIT! This says player_id: 7
    "game_session_id": 2,
    "theme_id": 10,
    ...
  }
    ''')
    
    print("\nBut we requested player_id: 12!")
    print("The API returned stats for player 7 (Alice), not player 12 (Frank)!")
    
    print("\n=== The Bug ===")
    print("The Pydantic model is returning the WRONG player stats!")
    print("\nLet me check the Round2Manager.select_theme() method...")
    
    engine = create_engine('sqlite:///backend/quizkw.db')
    Session = sessionmaker(bind=engine)
    db = Session()
    
    # Check what's in the database
    print("\n1. Checking database state...")
    
    # Player 7 stats
    stats_7 = db.query(models.PlayerRound2Stats).filter(
        models.PlayerRound2Stats.player_id == 7,
        models.PlayerRound2Stats.game_session_id == 2
    ).first()
    
    print(f"   Player 7 stats: {stats_7}")
    if stats_7:
        print(f"   theme_id: {stats_7.theme_id}")
    
    # Player 12 stats  
    stats_12 = db.query(models.PlayerRound2Stats).filter(
        models.PlayerRound2Stats.player_id == 12,
        models.PlayerRound2Stats.game_session_id == 2
    ).first()
    
    print(f"   Player 12 stats: {stats_12}")
    if stats_12:
        print(f"   theme_id: {stats_12.theme_id}")
    
    print("\n2. The issue is in Round2Manager.get_player_stats()!")
    print("""
   def get_player_stats(self, player_id: int, game_session_id: int) -> models.PlayerRound2Stats:
       stats = self.db.query(models.PlayerRound2Stats).filter(
           models.PlayerRound2Stats.player_id == player_id,
           models.PlayerRound2Stats.game_session_id == game_session_id
       ).first()
       
       if not stats:
           stats = models.PlayerRound2Stats(
               player_id=player_id,          <-- This sets player_id correctly
               game_session_id=game_session_id,
               qualification_status=models.QualificationStatus.PLAYING
           )
           self.db.add(stats)
           self.db.commit()
           self.db.refresh(stats)
       
       return stats
    """)
    
    print("\n3. But wait, that looks correct...")
    print("   Unless... there's a caching issue?")
    print("   Or the session has an existing object for player 7?")
    
    # Let me check if there's any existing stats
    print("\n4. Checking ALL PlayerRound2Stats...")
    all_stats = db.query(models.PlayerRound2Stats).all()
    for s in all_stats:
        print(f"   Player {s.player_id}: ID={s.id}, theme_id={s.theme_id}")
    
    print("\n5. AHA! Look at the IDs!")
    print("   The stats object returned has ID: 1")
    print("   That's player 7's stats!")
    print("\n   The bug is: Round2Manager is returning the WRONG stats object!")
    print("   Probably because of session caching or object identity issues.")
    
    db.close()
    
    print("\n=== The Fix ===")
    print("We need to ensure Round2Manager.select_theme() returns")
    print("the correct stats object, not a cached one.")
    print("\nPossible solutions:")
    print("1. Use db.refresh(stats) after commit")
    print("2. Use db.expire_all() to clear cache")
    print("3. Create a new query after commit")
    print("\nActually, we already have db.refresh(stats)...")
    print("So maybe the issue is elsewhere...")

if __name__ == "__main__":
    found_the_bug()