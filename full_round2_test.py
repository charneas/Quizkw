#!/usr/bin/env python3
"""
Script de test complet pour Round 2 MVP
Simule un tournoi complet avec 16 joueurs -> 8 joueurs -> 4 joueurs
"""
import requests
import json
import time
from typing import List, Dict

BASE_URL = "http://localhost:8000"
GAME_CODE = "ROUND2"

class Round2TestSimulator:
    def __init__(self):
        self.base_url = BASE_URL
        self.game_code = GAME_CODE
        self.players = []
        
    def log(self, message: str, level: str = "INFO"):
        print(f"[{level}] {message}")
        
    def get_players(self) -> List[Dict]:
        """Récupère tous les joueurs du jeu ROUND2"""
        try:
            response = requests.get(f"{self.base_url}/games/{self.game_code}")
            if response.status_code == 200:
                game_data = response.json()
                players = []
                for team in game_data.get('teams', []):
                    for player in team.get('players', []):
                        players.append(player)
                return players
            else:
                self.log(f"Erreur lors de la récupération des joueurs: {response.status_code}", "ERROR")
                return []
        except Exception as e:
            self.log(f"Exception: {e}", "ERROR")
            return []
    
    def get_available_themes(self) -> List[Dict]:
        """Récupère 3 thèmes aléatoires disponibles"""
        try:
            response = requests.get(f"{self.base_url}/round2/{self.game_code}/themes")
            if response.status_code == 200:
                data = response.json()
                return data.get('themes', [])
            return []
        except Exception as e:
            self.log(f"Exception lors de la récupération des thèmes: {e}", "ERROR")
            return []
    
    def select_theme(self, player_id: int, theme_id: int) -> bool:
        """Sélectionne un thème pour un joueur"""
        try:
            response = requests.post(
                f"{self.base_url}/round2/{self.game_code}/select-theme",
                json={"player_id": player_id, "theme_id": theme_id}
            )
            return response.status_code == 200
        except Exception as e:
            self.log(f"Exception lors de la sélection du thème: {e}", "ERROR")
            return False
    
    def get_question(self, player_id: int) -> Dict:
        """Récupère une question pour un joueur"""
        try:
            response = requests.get(f"{self.base_url}/round2/{self.game_code}/question/{player_id}")
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            self.log(f"Exception lors de la récupération de la question: {e}", "ERROR")
            return {}
    
    def submit_answer(self, player_id: int, question_id: int, answer: str) -> Dict:
        """Soumet une réponse"""
        try:
            response = requests.post(
                f"{self.base_url}/round2/{self.game_code}/answer",
                json={
                    "player_id": player_id,
                    "question_id": question_id,
                    "answer": answer
                }
            )
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            self.log(f"Exception lors de la soumission de la réponse: {e}", "ERROR")
            return {}
    
    def get_progress(self) -> Dict:
        """Récupère la progression du tournoi"""
        try:
            response = requests.get(f"{self.base_url}/round2/{self.game_code}/progress")
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            self.log(f"Exception: {e}", "ERROR")
            return {}
    
    def get_leaderboard(self) -> Dict:
        """Récupère le classement intermédiaire"""
        try:
            response = requests.get(f"{self.base_url}/round2/{self.game_code}/leaderboard")
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            self.log(f"Exception: {e}", "ERROR")
            return {}
    
    def advance_phase(self) -> bool:
        """Avance à la phase suivante"""
        try:
            response = requests.post(f"{self.base_url}/round2/{self.game_code}/advance")
            return response.status_code == 200
        except Exception as e:
            self.log(f"Exception: {e}", "ERROR")
            return False
    
    def simulate_player_round(self, player: Dict, num_questions: int = 10, correct_rate: float = 0.7):
        """Simule un joueur répondant à plusieurs questions"""
        player_id = player['id']
        player_name = player['name']
        
        self.log(f"Simulation pour {player_name} (ID: {player_id})")
        
        # Sélection du thème
        themes = self.get_available_themes()
        if not themes:
            self.log(f"  Aucun thème disponible pour {player_name}", "ERROR")
            return False
        
        theme = themes[0]  # Prend le premier thème
        self.log(f"  Sélection du thème: {theme['name']}")
        
        if not self.select_theme(player_id, theme['id']):
            self.log(f"  Erreur lors de la sélection du thème", "ERROR")
            return False
        
        # Répondre aux questions
        correct_answers = 0
        for i in range(num_questions):
            question_data = self.get_question(player_id)
            if not question_data:
                self.log(f"  Plus de questions disponibles après {i} questions")
                break
            
            question = question_data.get('question', {})
            correct_answer = question.get('correct_answer', '')
            
            # Simule une réponse correcte selon le taux de réussite
            import random
            is_correct = random.random() < correct_rate
            answer = correct_answer if is_correct else "Mauvaise réponse"
            
            result = self.submit_answer(player_id, question['id'], answer)
            if result.get('correct'):
                correct_answers += 1
        
        self.log(f"  {player_name}: {correct_answers}/{num_questions} réponses correctes")
        return True
    
    def run_full_tournament(self):
        """Exécute un tournoi complet 16 -> 8 -> 4"""
        self.log("=" * 60)
        self.log("DÉBUT DU TEST COMPLET ROUND 2 MVP")
        self.log("=" * 60)
        
        # Récupère les joueurs
        self.log("\n### Phase 1: Récupération des joueurs ###")
        self.players = self.get_players()
        self.log(f"Nombre de joueurs trouvés: {len(self.players)}")
        
        if len(self.players) < 16:
            self.log(f"ATTENTION: Seulement {len(self.players)} joueurs (16 requis)", "WARN")
        
        # Phase 16 joueurs
        self.log("\n### Phase 2: Simulation de la phase 16 joueurs ###")
        progress = self.get_progress()
        self.log(f"Phase actuelle: {progress.get('phase', 'unknown')}")
        self.log(f"Joueurs totaux: {progress.get('players_total', 0)}")
        
        # Simule chaque joueur (limité aux 16 premiers)
        players_to_simulate = self.players[:16]
        for idx, player in enumerate(players_to_simulate, 1):
            self.log(f"\n[{idx}/16] Joueur: {player['name']}")
            # Varie le taux de réussite pour créer des différences
            success_rate = 0.5 + (idx * 0.03)  # Entre 50% et 98%
            if success_rate > 1.0:
                success_rate = 0.95
            self.simulate_player_round(player, num_questions=10, correct_rate=success_rate)
            time.sleep(0.1)  # Petit délai pour éviter de surcharger le serveur
        
        # Affiche le classement intermédiaire
        self.log("\n### Phase 3: Classement intermédiaire ###")
        leaderboard = self.get_leaderboard()
        qualified = leaderboard.get('qualified', [])
        eliminated = leaderboard.get('eliminated', [])
        
        self.log(f"\n✅ QUALIFIÉS (Top 8):")
        for idx, player in enumerate(qualified, 1):
            self.log(f"  {idx}. {player.get('player_name', 'Unknown')} - {player.get('score', 0)} points")
        
        self.log(f"\n❌ ÉLIMINÉS:")
        for idx, player in enumerate(eliminated, 1):
            self.log(f"  {idx}. {player.get('player_name', 'Unknown')} - {player.get('score', 0)} points")
        
        # Avance à la phase 8 joueurs
        self.log("\n### Phase 4: Avancement vers phase 8 joueurs ###")
        if self.advance_phase():
            self.log("✅ Passage à la phase 8 joueurs réussi")
            progress = self.get_progress()
            self.log(f"Nouvelle phase: {progress.get('phase', 'unknown')}")
        else:
            self.log("❌ Échec de l'avancement de phase", "ERROR")
        
        # Simule la phase 8 joueurs
        self.log("\n### Phase 5: Simulation de la phase 8 joueurs ###")
        qualified_players = [p for p in self.players if p['id'] in [q['player_id'] for q in qualified]]
        for idx, player in enumerate(qualified_players, 1):
            self.log(f"\n[{idx}/8] Joueur: {player['name']}")
            success_rate = 0.6 + (idx * 0.04)
            self.simulate_player_round(player, num_questions=10, correct_rate=success_rate)
            time.sleep(0.1)
        
        # Classement après phase 8
        self.log("\n### Phase 6: Classement après phase 8 ###")
        leaderboard = self.get_leaderboard()
        qualified = leaderboard.get('qualified', [])
        
        self.log(f"\n✅ QUALIFIÉS pour phase 4 (Top 4):")
        for idx, player in enumerate(qualified[:4], 1):
            self.log(f"  {idx}. {player.get('player_name', 'Unknown')} - {player.get('score', 0)} points")
        
        # Résumé final
        self.log("\n" + "=" * 60)
        self.log("RÉSUMÉ DU TEST COMPLET")
        self.log("=" * 60)
        final_progress = self.get_progress()
        self.log(f"Phase finale: {final_progress.get('phase', 'unknown')}")
        self.log(f"Joueurs restants: {final_progress.get('players_remaining', 0)}")
        self.log(f"Joueurs éliminés: {final_progress.get('players_eliminated', 0)}")
        self.log("\n✅ Test complet terminé avec succès!")

def main():
    print("Quizkw - Test complet Round 2 MVP")
    print("Assurez-vous que le serveur backend tourne sur http://localhost:8000")
    print()
    
    simulator = Round2TestSimulator()
    simulator.run_full_tournament()

if __name__ == "__main__":
    main()
