"""
Script ponctuel (playtest 2026-08-15) : complète à 5+ questions HARD les
thèmes existants qui en manquaient pour rester éligibles à la Manche 3
(get_available_themes_for_selection exige >= 5 questions HARD par thème).

Réutilise le pipeline Wikipedia -> Claude déjà en place pour la génération de
contenu admin (app/wikipedia_client.py, app/content_generator.py), mais cible
un THÈME EXISTANT au lieu d'en créer un nouveau, et ne garde que les
questions générées en difficulté HARD (le reste est jeté).

Usage : ANTHROPIC_API_KEY=... python scripts/backfill_hard_questions.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Question, Theme, Difficulty, ThemeCategory
from app.wikipedia_client import get_wikipedia_extract
from app.content_generator import generate_content
from app.schemas import ThemeCategoryEnum

# (nom du thème existant, sujet Wikipedia à utiliser comme source)
TARGETS = [
    ("Espace & Astronomie", "Astronomie"),
    ("Technologie & Informatique", "Histoire de l'informatique"),
    ("Bandes Dessinées & Comics", "Bande dessinée"),
    ("Records du Monde", "Guinness World Records"),
    ("Langues & Étymologie", "Étymologie"),
]

MIN_HARD_QUESTIONS = 5
DIFFICULTY_POINTS = {"easy": 1, "medium": 2, "hard": 3}


def main():
    db = SessionLocal()
    try:
        for theme_name, wiki_topic in TARGETS:
            theme = db.query(Theme).filter(Theme.name == theme_name).first()
            if not theme:
                print(f"[SKIP] Thème introuvable en base : {theme_name}")
                continue

            existing_hard = db.query(Question).filter(
                Question.theme_id == theme.id, Question.difficulty == Difficulty.HARD
            ).count()
            if existing_hard >= MIN_HARD_QUESTIONS:
                print(f"[OK] {theme_name} a déjà {existing_hard} questions HARD, rien à faire.")
                continue

            needed = MIN_HARD_QUESTIONS - existing_hard
            print(f"[GEN] {theme_name} : {existing_hard} HARD existantes, {needed} à ajouter (sujet '{wiki_topic}')")

            try:
                extract = get_wikipedia_extract(wiki_topic)
            except (LookupError, ValueError) as e:
                print(f"[ERREUR] Wikipedia pour '{wiki_topic}' : {e}")
                continue

            category = ThemeCategoryEnum(theme.category.value)
            collected_hard = []
            attempts = 0
            # Un seul appel ne garantit pas assez de HARD (mix easy/medium/hard
            # non contrôlé) — on relance jusqu'à obtenir assez de HARD ou un
            # nombre raisonnable de tentatives pour ne pas boucler indéfiniment.
            while len(collected_hard) < needed and attempts < 4:
                attempts += 1
                try:
                    generated = generate_content(wiki_topic, extract, category)
                except (ValueError, RuntimeError) as e:
                    print(f"[ERREUR] Génération Claude (tentative {attempts}) : {e}")
                    continue

                new_hard = [q for q in generated.questions if q.difficulty.value == "hard"]
                # Évite les doublons de texte entre tentatives successives.
                existing_texts = {q.text for q in collected_hard}
                for q in new_hard:
                    if q.text not in existing_texts:
                        collected_hard.append(q)
                        existing_texts.add(q.text)
                print(f"  tentative {attempts} : +{len(new_hard)} HARD générées (total retenu : {len(collected_hard)})")

            to_insert = collected_hard[:needed]
            if len(to_insert) < needed:
                print(f"[ATTENTION] {theme_name} : seulement {len(to_insert)}/{needed} obtenues après {attempts} tentatives.")

            max_number = db.query(Question).filter(Question.theme_id == theme.id).count()
            for i, q in enumerate(to_insert, start=1):
                question = Question(
                    text=q.text,
                    category=theme_name,
                    difficulty=Difficulty.HARD,
                    points=DIFFICULTY_POINTS["hard"],
                    correct_answer=q.correct_answer,
                    wrong_answers=json.dumps(q.wrong_answers),
                    theme_id=theme.id,
                    question_number=max_number + i,
                )
                db.add(question)
                print(f"  + {question.text[:80]}")

            db.commit()
            print(f"[FAIT] {theme_name} : {len(to_insert)} question(s) HARD ajoutée(s).\n")
    finally:
        db.close()


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY manquante dans l'environnement.")
        sys.exit(1)
    main()
