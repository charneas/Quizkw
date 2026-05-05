#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# ///

"""
Script d'initialisation du sanctuaire pour l'agent Le Boss.
Crée la structure de mémoire et copie les templates dans le sanctuaire.
"""

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
    "PULSE-template.md"
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
    if len(sys.argv) != 3:
        print("Usage: python3 init-sanctum.py <project-root> <skill-path>")
        sys.exit(1)
    
    project_root = sys.argv[1]
    skill_path = sys.argv[2]
    
    try:
        create_sanctum_structure(project_root, skill_path)
    except Exception as e:
        print(f"❌ Erreur lors de l'initialisation : {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()