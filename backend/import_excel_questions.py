#!/usr/bin/env python3
"""
Script pour importer les questions depuis le fichier Excel
Lit l'onglet "Questions Finale" et crée des questions HARD pour Round 3
"""

import pandas as pd
import json
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Question, Difficulty

def import_questions_from_excel(excel_path: str):
    """Importer les questions depuis le fichier Excel"""
    
    db = SessionLocal()
    
    try:
        # Lire l'onglet "Questions Finale"
        df = pd.read_excel(excel_path, sheet_name="Questions Finale")
        
        print(f"📖 Lecture du fichier Excel: {excel_path}")
        print(f"   Lignes trouvées: {len(df)}")
        
        question_count = 0
        
        # Parcourir chaque ligne (thème)
        for idx, row in df.iterrows():
            theme = row.iloc[1]  # Colonne B (index 1)
            
            if pd.isna(theme) or theme == "":
                continue
                
            print(f"\n🎯 Thème: {theme}")
            
            # Parcourir les 5 paires question/réponse
            for i in range(5):
                # Colonnes: C/D (2/3), E/F (4/5), G/H (6/7), I/J (8/9), K/L (10/11)
                question_col = 2 + (i * 2)
                answer_col = 3 + (i * 2)
                
                question_text = row.iloc[question_col]
                correct_answer = row.iloc[answer_col]
                
                # Vérifier que la question et la réponse existent
                if pd.isna(question_text) or pd.isna(correct_answer):
                    continue
                
                if question_text == "" or correct_answer == "":
                    continue
                
                # Créer des réponses incorrectes génériques
                # (Dans un vrai système, il faudrait les définir manuellement)
                wrong_answers = [
                    f"Réponse incorrecte A",
                    f"Réponse incorrecte B",
                    f"Réponse incorrecte C"
                ]
                
                # Créer la question en base
                question = Question(
                    text=str(question_text).strip(),
                    category=str(theme).strip(),
                    difficulty=Difficulty.HARD,
                    points=6,
                    correct_answer=str(correct_answer).strip(),
                    wrong_answers=json.dumps(wrong_answers)
                )
                
                db.add(question)
                question_count += 1
                
                print(f"   ✅ Question {i+1}: {question_text[:50]}...")
        
        db.commit()
        
        print(f"\n✨ Import terminé !")
        print(f"   {question_count} questions HARD importées")
        print(f"\n📊 Total des questions en base:")
        print(f"   {db.query(Question).count()} questions")
        
    except FileNotFoundError:
        print(f"❌ Fichier non trouvé: {excel_path}")
        print(f"   Assurez-vous que le fichier est au bon emplacement")
    except Exception as e:
        db.rollback()
        print(f"❌ Erreur lors de l'import: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    
    # Chemin par défaut
    default_path = "c:/Users/sebas/OneDrive/Documents/6 ans kw/Quiz/Questions Themes.xlsx"
    
    if len(sys.argv) > 1:
        excel_path = sys.argv[1]
    else:
        excel_path = default_path
        
    print("🧪 Import des questions depuis Excel")
    print(f"   Fichier: {excel_path}\n")
    
    import_questions_from_excel(excel_path)
