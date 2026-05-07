#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# ///

"""
Script d'initialisation du sanctuaire pour l'agent Le Boss.
Crée la structure de mémoire et copie les templates dans le sanctuaire.
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# Configuration
SKILL_NAME = "agent-le-boss"
SKILL_ONLY_FILES = ["first-breath.md"]
TEMPLATE_FILES = [
    "PERSONA-template.md",
    "CREED-template.md", 
    "BOND-template.md",
    "MEMORY-template.md",
    "CAPABILITIES-template.md",
    "PULSE-template.md",
    "INDEX-template.md"
]
EVOLVABLE = False

def create_sanctum_structure(project_root, skill_path):
    """Crée la structure complète du sanctuaire."""
    
    # Chemins
    sanctum_path = Path(project_root) / "_bmad" / "memory" / SKILL_NAME
    skill_assets_path = Path(skill_path) / "assets"
    skill_references_path = Path(skill_path) / "references"
    
    print(f"Initialisation du sanctuaire pour {SKILL_NAME}...")
    print(f"Sanctuaire : {sanctum_path}")
    
    # Créer le répertoire du sanctuaire
    sanctum_path.mkdir(parents=True, exist_ok=True)
    
    # Copier les fichiers spécifiques au skill
    for file_name in SKILL_ONLY_FILES:
        source_file = skill_references_path / file_name
        if source_file.exists():
            shutil.copy2(source_file, sanctum_path / file_name)
            print(f"✓ Copié {file_name}")
        else:
            print(f"⚠ Fichier non trouvé : {source_file}")
    
    # Copier et renommer les templates
    for template_file in TEMPLATE_FILES:
        source_template = skill_assets_path / template_file
        if source_template.exists():
            # Enlever le suffixe -template
            target_name = template_file.replace("-template", "")
            shutil.copy2(source_template, sanctum_path / target_name)
            print(f"✓ Créé {target_name}")
        else:
            print(f"⚠ Template non trouvé : {source_template}")
    
    # Créer les sous-répertoires de mémoire
    memory_dirs = ["logs", "references", "boundaries", "learned"]
    for dir_name in memory_dirs:
        (sanctum_path / dir_name).mkdir(exist_ok=True)
        print(f"✓ Créé répertoire {dir_name}/")
    
    # Créer les fichiers de base de mémoire
    index_content = """# Index de Mémoire

## Structure
- `logs/` - Historique des sessions
- `references/` - Documents de référence
- `boundaries/` - Limites d'accès
- `learned/` - Capacités apprises

## Dernière Session
Aucune session enregistrée.
"""
    
    (sanctum_path / "index.md").write_text(index_content, encoding="utf-8")
    print("✓ Créé index.md")
    
    print(f"\n✅ Sanctuaire initialisé avec succès !")
    print(f"📍 Emplacement : {sanctum_path}")

def main():
    parser = argparse.ArgumentParser(
        description="Initialise le sanctuaire pour l'agent Le Boss",
        epilog="Exemple: python init-sanctum.py /chemin/vers/projet /chemin/vers/skill"
    )
    parser.add_argument(
        "project_root",
        help="Racine du projet (contenant _bmad/)"
    )
    parser.add_argument(
        "skill_path", 
        help="Chemin vers le répertoire du skill (skills/agent-le-boss)"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Sortie au format JSON"
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Simule l'initialisation sans créer de fichiers"
    )
    
    args = parser.parse_args()
    
    try:
        if args.dry_run:
            print(f"Simulation: Initialisation du sanctuaire pour {SKILL_NAME}")
            print(f"Project root: {args.project_root}")
            print(f"Skill path: {args.skill_path}")
            print(f"Templates: {len(TEMPLATE_FILES)} fichiers")
            print(f"Skill-only files: {SKILL_ONLY_FILES}")
            result = {
                "status": "dry_run",
                "skill_name": SKILL_NAME,
                "project_root": args.project_root,
                "skill_path": args.skill_path,
                "templates_count": len(TEMPLATE_FILES),
                "skill_only_files": SKILL_ONLY_FILES
            }
        else:
            create_sanctum_structure(args.project_root, args.skill_path)
            result = {
                "status": "success",
                "skill_name": SKILL_NAME,
                "sanctum_path": str(Path(args.project_root) / "_bmad" / "memory" / SKILL_NAME),
                "templates_copied": len(TEMPLATE_FILES),
                "directories_created": 4  # logs, references, boundaries, learned
            }
        
        if args.json:
            print(json.dumps(result, indent=2))
        elif not args.dry_run:
            print(f"\n✅ Sanctuaire initialisé avec succès !")
            print(f"📍 Emplacement : {Path(args.project_root) / '_bmad' / 'memory' / SKILL_NAME}")
            
    except Exception as e:
        error_result = {
            "status": "error",
            "skill_name": SKILL_NAME,
            "error": str(e)
        }
        if args.json:
            print(json.dumps(error_result, indent=2))
        else:
            print(f"❌ Erreur lors de l'initialisation : {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
