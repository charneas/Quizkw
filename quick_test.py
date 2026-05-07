#!/usr/bin/env python3
import requests
import json

BASE_URL = "http://localhost:8000"

print("=== Quick test after schema fix ===")

# 1. Health check
try:
    resp = requests.get(f"{BASE_URL}/health", timeout=5)
    print(f"1. Health: {resp.status_code} - {resp.json()}")
except Exception as e:
    print(f"1. Health error: {e}")

# 2. Test ROUND2 endpoint
print("\n2. Testing ROUND2 endpoint:")
try:
    resp = requests.get(f"{BASE_URL}/games/ROUND2", timeout=10)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        game = resp.json()
        print(f"   Success! Game code: {game.get('code')}")
        print(f"   Teams: {len(game.get('teams', []))}")
        print(f"   Players: {sum(len(t.get('players', [])) for t in game.get('teams', []))}")
        # Check if players have team_id = None
        for i, team in enumerate(game.get('teams', [])):
            for j, player in enumerate(team.get('players', [])):
                if j < 2:  # Show first 2 players per team
                    print(f"   Team {i+1}, Player {j+1}: {player.get('name')}, team_id: {player.get('team_id')}")
    elif resp.status_code == 500:
        print(f"   Error 500: {resp.text}")
        # Try to get error details
        try:
            error_json = resp.json()
            print(f"   Error JSON: {json.dumps(error_json, indent=2)}")
        except:
            pass
except Exception as e:
    print(f"   Exception: {e}")
    import traceback
    traceback.print_exc()

# 3. Test Round 2 themes
print("\n3. Testing Round 2 themes:")
try:
    resp = requests.get(f"{BASE_URL}/round2/ROUND2/themes", timeout=5)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"   Themes count: {len(data.get('themes', []))}")
        print(f"   Game session ID: {data.get('game_session_id')}")
except Exception as e:
    print(f"   Exception: {e}")

# 4. Test Round 2 progress
print("\n4. Testing Round 2 progress:")
try:
    resp = requests.get(f"{BASE_URL}/round2/ROUND2/progress", timeout=5)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"   Phase: {data.get('phase')}")
        print(f"   Players total: {data.get('players_total')}")
except Exception as e:
    print(f"   Exception: {e}")

print("\n=== Test complete ===")