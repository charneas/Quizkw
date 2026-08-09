from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from datetime import datetime
from typing import Dict, Optional, List
from . import models, schemas


class PingPongManager:
    """Manager pour la logique métier des duels Ping-Pong (format 1v1 tour par tour)"""

    def __init__(self, db: Session):
        self.db = db

    def start_duel(
        self,
        game_session_id: int,
        theme_id: int,
        team1_id: int,
        team2_id: int,
    ) -> models.PingPongDuel:
        """
        Créer un nouveau duel ping-pong entre 2 équipes.
        team1 est l'équipe qui a tourné la roue (elle commence).
        """
        # Vérifier que le thème existe
        theme = (
            self.db.query(models.PingPongTheme)
            .filter(models.PingPongTheme.id == theme_id)
            .first()
        )
        if not theme:
            raise ValueError(f"Ping-pong theme with ID {theme_id} not found")

        # Vérifier que les deux équipes existent dans cette session
        team1 = (
            self.db.query(models.Team)
            .filter(
                models.Team.id == team1_id,
                models.Team.game_session_id == game_session_id,
            )
            .first()
        )
        team2 = (
            self.db.query(models.Team)
            .filter(
                models.Team.id == team2_id,
                models.Team.game_session_id == game_session_id,
            )
            .first()
        )
        if not team1 or not team2:
            raise ValueError("One or both teams not found in this game session")

        if team1_id == team2_id:
            raise ValueError("A team cannot duel itself")

        # Empêche une équipe de se retrouver dans 2 duels actifs simultanés
        # (BUG-101c) : use_token (SWAP) et get_team_specific_state
        # recherchent "le" duel actif d'une équipe via .first() sans critère
        # de désambiguïsation — s'il en existait plusieurs, l'un d'eux serait
        # choisi arbitrairement et pourrait recevoir l'effet d'un jeton ou
        # un état affiché destiné à l'autre.
        existing_active_duel = (
            self.db.query(models.PingPongDuel)
            .filter(
                models.PingPongDuel.game_session_id == game_session_id,
                models.PingPongDuel.is_completed == False,
                or_(
                    models.PingPongDuel.team1_id.in_([team1_id, team2_id]),
                    models.PingPongDuel.team2_id.in_([team1_id, team2_id]),
                ),
            )
            .first()
        )
        if existing_active_duel:
            raise ValueError(
                "One of the teams already has an active ping-pong duel"
            )

        # Créer le duel
        duel = models.PingPongDuel(
            game_session_id=game_session_id,
            theme_id=theme_id,
            team1_id=team1_id,
            team2_id=team2_id,
            current_turn_team_id=team1_id,  # L'équipe qui a choisi commence
            is_completed=False,
            answers_used=[],
        )

        self.db.add(duel)
        self.db.commit()
        self.db.refresh(duel)

        return duel

    def submit_answer(
        self, duel_id: int, team_id: int, answer: str
    ) -> Dict:
        """
        Soumettre une réponse dans un duel ping-pong.
        
        Logique:
        - Vérifier que c'est bien le tour de cette équipe
        - Normaliser la réponse (lower, strip)
        - Vérifier qu'elle est dans la liste des réponses valides
        - Vérifier qu'elle n'a pas déjà été donnée (doublon)
        
        Si correcte:
          - Ajouter aux answers_used
          - Créer un PingPongTurn
          - Changer current_turn_team_id vers l'autre équipe
          - Retourner {duel_continues: True, next_turn_team_id: ...}
        
        Si incorrecte:
          - Marquer le duel comme terminé
          - L'autre équipe gagne
          - Calculer les points: +2 par réponse correcte donnée par le gagnant
          - Retourner {duel_continues: False, winner_team_id: ...}
        """
        # Récupérer le duel
        duel = (
            self.db.query(models.PingPongDuel)
            .filter(models.PingPongDuel.id == duel_id)
            .first()
        )
        if not duel:
            raise ValueError(f"Duel with ID {duel_id} not found")

        if duel.is_completed:
            raise ValueError("This duel is already completed")

        # Vérifier que c'est le tour de cette équipe
        if duel.current_turn_team_id != team_id:
            raise ValueError("It's not this team's turn")

        # Récupérer le thème pour les réponses valides
        theme = (
            self.db.query(models.PingPongTheme)
            .filter(models.PingPongTheme.id == duel.theme_id)
            .first()
        )
        if not theme:
            raise ValueError(f"Theme with ID {duel.theme_id} not found")

        # Normaliser les réponses
        normalized_answer = answer.strip().lower()
        correct_answers_lower = [
            ans.strip().lower() for ans in theme.correct_answers
        ]
        answers_used_lower = [
            ans.strip().lower() for ans in (duel.answers_used or [])
        ]

        # Déterminer le numéro du tour actuel
        current_turn_number = (
            self.db.query(func.count(models.PingPongTurn.id))
            .filter(models.PingPongTurn.duel_id == duel_id)
            .scalar()
            + 1
        )

        # Vérifier si la réponse est correcte
        if normalized_answer not in correct_answers_lower:
            # Mauvaise réponse → l'équipe perd, l'autre gagne
            loser_team_id = team_id
            winner_team_id = duel.team2_id if team_id == duel.team1_id else duel.team1_id

            # Enregistrer le tour (mauvaise réponse)
            turn = models.PingPongTurn(
                duel_id=duel_id,
                team_id=team_id,
                answer_given=answer.strip(),
                is_correct=False,
                turn_number=current_turn_number,
            )
            self.db.add(turn)

            # Points du gagnant: +2 points fixes pour la victoire du duel
            winner_points = 2

            # Mettre à jour le duel
            duel.winner_team_id = winner_team_id
            duel.is_completed = True
            duel.answers_used = duel.answers_used or []

            # Ajouter les points à l'équipe gagnante
            winner_team = (
                self.db.query(models.Team)
                .filter(models.Team.id == winner_team_id)
                .first()
            )
            if winner_team:
                winner_team.score += winner_points

            self.db.commit()
            self.db.refresh(duel)

            winner_team_obj = (
                self.db.query(models.Team)
                .filter(models.Team.id == winner_team_id)
                .first()
            )

            return {
                "is_correct": False,
                "answer": answer.strip(),
                "turn_number": current_turn_number,
                "duel_continues": False,
                "winner_team_id": winner_team_id,
                "winner_team_name": winner_team_obj.name if winner_team_obj else None,
                "next_turn_team_id": None,
                "message": f"Mauvaise réponse ! {winner_team_obj.name if winner_team_obj else 'Autre équipe'} remporte le duel (+{winner_points} pts)",
            }

        # Vérifier que la réponse n'a pas déjà été donnée
        if normalized_answer in answers_used_lower:
            # La réponse a déjà été donnée → c'est comme une mauvaise réponse
            loser_team_id = team_id
            winner_team_id = duel.team2_id if team_id == duel.team1_id else duel.team1_id

            turn = models.PingPongTurn(
                duel_id=duel_id,
                team_id=team_id,
                answer_given=answer.strip(),
                is_correct=False,
                turn_number=current_turn_number,
            )
            self.db.add(turn)

            # Points du gagnant: +2 points fixes pour la victoire du duel
            winner_points = 2

            duel.winner_team_id = winner_team_id
            duel.is_completed = True

            winner_team = (
                self.db.query(models.Team)
                .filter(models.Team.id == winner_team_id)
                .first()
            )
            if winner_team:
                winner_team.score += winner_points

            self.db.commit()
            self.db.refresh(duel)

            winner_team_obj = (
                self.db.query(models.Team)
                .filter(models.Team.id == winner_team_id)
                .first()
            )

            return {
                "is_correct": False,
                "answer": answer.strip(),
                "turn_number": current_turn_number,
                "duel_continues": False,
                "winner_team_id": winner_team_id,
                "winner_team_name": winner_team_obj.name if winner_team_obj else None,
                "next_turn_team_id": None,
                "message": f"Réponse déjà donnée ! {winner_team_obj.name if winner_team_obj else 'Autre équipe'} remporte le duel (+{winner_points} pts)",
            }

        # Bonne réponse, non-doublon
        turn = models.PingPongTurn(
            duel_id=duel_id,
            team_id=team_id,
            answer_given=answer.strip(),
            is_correct=True,
            turn_number=current_turn_number,
        )
        self.db.add(turn)

        # Ajouter aux réponses utilisées
        updated_answers = list(duel.answers_used or [])
        updated_answers.append(answer.strip())
        duel.answers_used = updated_answers

        # Déterminer l'autre équipe
        other_team_id = duel.team2_id if team_id == duel.team1_id else duel.team1_id

        # Changer le tour vers l'autre équipe
        duel.current_turn_team_id = other_team_id

        self.db.commit()
        self.db.refresh(duel)

        other_team = (
            self.db.query(models.Team).filter(models.Team.id == other_team_id).first()
        )

        return {
            "is_correct": True,
            "answer": answer.strip(),
            "turn_number": current_turn_number,
            "duel_continues": True,
            "winner_team_id": None,
            "winner_team_name": None,
            "next_turn_team_id": other_team_id,
            "message": f"Bonne réponse ! Au tour de {other_team.name if other_team else 'autre équipe'}",
        }

    def get_duel_state(self, duel_id: int) -> Dict:
        """Récupérer l'état actuel d'un duel"""
        duel = (
            self.db.query(models.PingPongDuel)
            .filter(models.PingPongDuel.id == duel_id)
            .first()
        )
        if not duel:
            raise ValueError(f"Duel with ID {duel_id} not found")

        theme = (
            self.db.query(models.PingPongTheme)
            .filter(models.PingPongTheme.id == duel.theme_id)
            .first()
        )

        # Compter les tours
        turns = (
            self.db.query(models.PingPongTurn)
            .filter(models.PingPongTurn.duel_id == duel_id)
            .order_by(models.PingPongTurn.turn_number)
            .all()
        )
        current_turn_number = len(turns) + 1

        team1 = (
            self.db.query(models.Team).filter(models.Team.id == duel.team1_id).first()
        )
        team2 = (
            self.db.query(models.Team).filter(models.Team.id == duel.team2_id).first()
        )
        current_turn_team = (
            self.db.query(models.Team)
            .filter(models.Team.id == duel.current_turn_team_id)
            .first()
        )

        return {
            "duel_id": duel.id,
            "theme": {
                "id": theme.id if theme else None,
                "title": theme.title if theme else None,
                "description": theme.description if theme else None,
                "correct_answers": theme.correct_answers if theme else [],
                "min_answers_to_win": theme.min_answers_to_win if theme else 3,
            },
            "team1": {
                "id": team1.id if team1 else None,
                "name": team1.name if team1 else None,
            },
            "team2": {
                "id": team2.id if team2 else None,
                "name": team2.name if team2 else None,
            },
            "current_turn_team_id": duel.current_turn_team_id,
            "current_turn_team_name": current_turn_team.name
            if current_turn_team
            else None,
            "turn_number": current_turn_number,
            "answers_used": duel.answers_used or [],
            "is_completed": duel.is_completed,
            "winner_team_id": duel.winner_team_id,
            "is_cancelled": duel.is_cancelled,
        }

    def cancel_duel(self, duel_id: int) -> models.PingPongDuel:
        """Annuler un duel bloqué (BUG-101g, story J.002). Action host uniquement.

        Libère les deux équipes (garde anti-double-duel de #54 filtre sur
        is_completed == False) sans jamais désigner de vainqueur ni toucher
        au score. Le duel de départage de fin de Manche 1 est hors périmètre :
        il est déjà couvert par un repli existant (#54).
        """
        duel = (
            self.db.query(models.PingPongDuel)
            .filter(models.PingPongDuel.id == duel_id)
            .first()
        )
        if not duel:
            raise ValueError(f"Duel with ID {duel_id} not found")

        if duel.is_completed:
            raise ValueError("Ce duel est déjà terminé")

        if duel.is_tiebreak:
            raise ValueError("Le duel de départage ne peut pas être annulé")

        duel.is_completed = True
        duel.is_cancelled = True
        self.db.commit()
        self.db.refresh(duel)

        return duel

    def get_duel_results(self, duel_id: int) -> Dict:
        """Récupérer les résultats finaux d'un duel"""
        duel = (
            self.db.query(models.PingPongDuel)
            .filter(models.PingPongDuel.id == duel_id)
            .first()
        )
        if not duel:
            raise ValueError(f"Duel with ID {duel_id} not found")

        if not duel.is_completed:
            raise ValueError("Duel is not yet completed")

        theme = (
            self.db.query(models.PingPongTheme)
            .filter(models.PingPongTheme.id == duel.theme_id)
            .first()
        )

        # Récupérer tous les tours
        all_turns = (
            self.db.query(models.PingPongTurn)
            .filter(models.PingPongTurn.duel_id == duel_id)
            .order_by(models.PingPongTurn.turn_number)
            .all()
        )

        team1 = (
            self.db.query(models.Team).filter(models.Team.id == duel.team1_id).first()
        )
        team2 = (
            self.db.query(models.Team).filter(models.Team.id == duel.team2_id).first()
        )
        winner_team = (
            self.db.query(models.Team)
            .filter(models.Team.id == duel.winner_team_id)
            .first()
        )

        # Calculer les stats par équipe
        team1_turns = [t for t in all_turns if t.team_id == duel.team1_id]
        team2_turns = [t for t in all_turns if t.team_id == duel.team2_id]
        team1_correct = [t for t in team1_turns if t.is_correct]
        team2_correct = [t for t in team2_turns if t.is_correct]

        return {
            "duel_id": duel.id,
            "theme": {
                "id": theme.id if theme else None,
                "title": theme.title if theme else None,
                "description": theme.description if theme else None,
                "correct_answers": theme.correct_answers if theme else [],
                "min_answers_to_win": theme.min_answers_to_win if theme else 3,
            },
            "team1": {
                "id": team1.id if team1 else None,
                "name": team1.name if team1 else None,
                "turns": len(team1_turns),
                "correct_answers": [
                    t.answer_given for t in team1_turns if t.is_correct
                ],
            },
            "team2": {
                "id": team2.id if team2 else None,
                "name": team2.name if team2 else None,
                "turns": len(team2_turns),
                "correct_answers": [
                    t.answer_given for t in team2_turns if t.is_correct
                ],
            },
            "winner_team_id": duel.winner_team_id,
            "winner_team_name": winner_team.name if winner_team else None,
            "total_turns": len(all_turns),
            "answers_used": duel.answers_used or [],
        }

    def get_random_theme(self) -> Optional[models.PingPongTheme]:
        """Récupérer un thème ping-pong aléatoire"""
        theme = (
            self.db.query(models.PingPongTheme)
            .order_by(func.random())
            .first()
        )
        return theme