#!/usr/bin/env python3
"""
Ajoute les 13 nouveaux thèmes Ping-Pong sans toucher aux thèmes existants
(donc sans casser l'historique des duels déjà joués dessus).
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app.models import Base, PingPongTheme

Base.metadata.create_all(bind=engine)

new_themes_data = [
    {
        "title": "Chanteurs et groupes de variété française",
        "description": "Citez des chanteurs ou groupes de variété française",
        "correct_answers": [
            "Johnny Hallyday", "Jean-Jacques Goldman", "Mylène Farmer",
            "Francis Cabrel", "Vanessa Paradis", "Patrick Bruel",
            "Renaud", "Charles Aznavour", "Edith Piaf", "Christophe Maé",
            "Zaz", "Stromae", "Angèle", "Indochine", "Téléphone",
            "Louane", "Julien Doré", "Vianney", "Kendji Girac",
            "Amir", "Slimane", "M Pokora", "Christophe Willem",
            "Grand Corps Malade", "Aya Nakamura"
        ],
        "min_answers_to_win": 4,
    },
    {
        "title": "Personnages de Disney",
        "description": "Citez des personnages issus des films Disney",
        "correct_answers": [
            "Mickey", "Minnie", "Donald", "Dingo", "Simba", "Mufasa",
            "Elsa", "Anna", "Olaf", "Ariel", "Belle", "Cendrillon",
            "Blanche-Neige", "Aladdin", "Jasmine", "Jafar", "Peter Pan",
            "Wendy", "Capitaine Crochet", "Pinocchio", "Bambi",
            "Dumbo", "Raiponce", "Flynn Rider", "Mulan", "Pocahontas",
            "Hercule", "Winnie l'ourson", "Tigrou", "Woody", "Buzz l'Éclair"
        ],
        "min_answers_to_win": 5,
    },
    {
        "title": "Fleuves et rivières de France",
        "description": "Citez des fleuves ou rivières français",
        "correct_answers": [
            "Seine", "Loire", "Rhône", "Garonne", "Rhin", "Meuse",
            "Moselle", "Marne", "Dordogne", "Somme", "Adour",
            "Charente", "Vienne", "Yonne", "Isère", "Durance",
            "Saône", "Oise", "Aisne", "Var", "Ain", "Lot", "Tarn"
        ],
        "min_answers_to_win": 3,
    },
    {
        "title": "Championnats du monde de football",
        "description": "Citez des pays vainqueurs de la Coupe du Monde de football",
        "correct_answers": [
            "Brésil", "Allemagne", "Italie", "Argentine", "France",
            "Uruguay", "Angleterre", "Espagne"
        ],
        "min_answers_to_win": 3,
    },
    {
        "title": "Animaux de la savane",
        "description": "Citez des animaux que l'on trouve dans la savane africaine",
        "correct_answers": [
            "Lion", "Éléphant", "Girafe", "Zèbre", "Guépard",
            "Hyène", "Rhinocéros", "Hippopotame", "Buffle",
            "Gnou", "Antilope", "Gazelle", "Léopard", "Autruche",
            "Chacal", "Phacochère", "Babouin", "Vautour", "Suricate"
        ],
        "min_answers_to_win": 4,
    },
    {
        "title": "Films d'animation Pixar",
        "description": "Citez des films d'animation produits par Pixar",
        "correct_answers": [
            "Toy Story", "1001 Pattes", "Monstres et Cie", "Némo",
            "Les Indestructibles", "Cars", "Ratatouille", "Wall-E",
            "Là-Haut", "Rebelle", "Vice-Versa", "Le Voyage d'Arlo",
            "Coco", "Les Indestructibles 2", "Toy Story 4", "En Avant",
            "Soul", "Luca", "Alerte Rouge", "Elemental"
        ],
        "min_answers_to_win": 4,
    },
    {
        "title": "Sports olympiques d'été",
        "description": "Citez des sports au programme des Jeux Olympiques d'été",
        "correct_answers": [
            "Athlétisme", "Natation", "Gymnastique", "Judo", "Escrime",
            "Cyclisme", "Aviron", "Voile", "Tir à l'arc", "Basketball",
            "Football", "Handball", "Volleyball", "Boxe", "Lutte",
            "Haltérophilie", "Tennis", "Tennis de table", "Badminton",
            "Rugby", "Skateboard", "Surf", "Escalade", "Équitation",
            "Water-polo", "Triathlon", "Pentathlon moderne"
        ],
        "min_answers_to_win": 5,
    },
    {
        "title": "Peintres célèbres",
        "description": "Citez des peintres célèbres",
        "correct_answers": [
            "Picasso", "Van Gogh", "Monet", "Renoir", "Léonard de Vinci",
            "Michel-Ange", "Rembrandt", "Dalí", "Matisse", "Cézanne",
            "Degas", "Gauguin", "Vermeer", "Rubens", "Klimt",
            "Munch", "Botticelli", "Caravage", "Delacroix", "Manet",
            "Toulouse-Lautrec", "Magritte", "Kandinsky", "Chagall"
        ],
        "min_answers_to_win": 4,
    },
    {
        "title": "Régions de France",
        "description": "Citez des régions administratives françaises",
        "correct_answers": [
            "Île-de-France", "Auvergne-Rhône-Alpes", "Bretagne",
            "Normandie", "Occitanie", "Nouvelle-Aquitaine",
            "Hauts-de-France", "Grand Est", "Provence-Alpes-Côte d'Azur",
            "Pays de la Loire", "Centre-Val de Loire", "Bourgogne-Franche-Comté",
            "Corse"
        ],
        "min_answers_to_win": 3,
    },
    {
        "title": "Instruments de musique",
        "description": "Citez des instruments de musique",
        "correct_answers": [
            "Guitare", "Piano", "Violon", "Batterie", "Trompette",
            "Saxophone", "Flûte", "Clarinette", "Violoncelle",
            "Contrebasse", "Harpe", "Accordéon", "Trombone", "Tuba",
            "Orgue", "Xylophone", "Banjo", "Ukulélé", "Cor",
            "Hautbois", "Basson", "Djembé", "Harmonica"
        ],
        "min_answers_to_win": 4,
    },
    {
        "title": "Super-héros DC Comics",
        "description": "Citez des super-héros de l'univers DC Comics",
        "correct_answers": [
            "Batman", "Superman", "Wonder Woman", "The Flash",
            "Aquaman", "Green Lantern", "Cyborg", "Green Arrow",
            "Shazam", "Robin", "Batgirl", "Nightwing", "Supergirl",
            "Martian Manhunter", "Hawkman", "Zatanna", "Black Canary"
        ],
        "min_answers_to_win": 4,
    },
    {
        "title": "Villes de plus d'un million d'habitants dans le monde",
        "description": "Citez des villes du monde comptant plus d'un million d'habitants",
        "correct_answers": [
            "Paris", "Londres", "New York", "Tokyo", "Pékin", "Shanghai",
            "Moscou", "Le Caire", "Mumbai", "Delhi", "São Paulo",
            "Mexico", "Los Angeles", "Istanbul", "Séoul", "Bangkok",
            "Berlin", "Madrid", "Rome", "Buenos Aires", "Lagos",
            "Karachi", "Jakarta", "Manille", "Rio de Janeiro"
        ],
        "min_answers_to_win": 4,
    },
]


def add_new_ping_pong_themes(db: Session):
    existing_titles = {t.title for t in db.query(PingPongTheme).all()}
    added = 0
    for theme_data in new_themes_data:
        if theme_data["title"] in existing_titles:
            print(f"⏭️  Déjà présent, ignoré : {theme_data['title']}")
            continue
        theme = PingPongTheme(
            title=theme_data["title"],
            description=theme_data["description"],
            correct_answers=theme_data["correct_answers"],
            min_answers_to_win=theme_data["min_answers_to_win"],
        )
        db.add(theme)
        added += 1
    db.commit()
    print(f"✅ {added} nouveaux thèmes Ping-Pong ajoutés")
    print(f"   - Total thèmes Ping-Pong en base : {db.query(PingPongTheme).count()}")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        add_new_ping_pong_themes(db)
    finally:
        db.close()
