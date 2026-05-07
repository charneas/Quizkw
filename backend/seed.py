#!/usr/bin/env python3
"""
Script de peuplement de la base de données pour les tests
Permet de créer des données de test réalistes pour le quiz
"""

import asyncio
import json
import random
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app.models import Base, Question, Difficulty, GameSession, Team, Player, Token, TokenType, RoundType, Theme, ThemeCategory, PlayerRound2Stats, QualificationStatus

# Créer toutes les tables
Base.metadata.create_all(bind=engine)

def seed_questions(db: Session):
    """Peupler la base avec des questions de test"""
    
    questions_data = [
        # Questions faciles (2 points)
        {
            "text": "Quelle est la capitale de la France ?",
            "category": "Géographie",
            "difficulty": Difficulty.EASY,
            "points": 2,
            "correct_answer": "Paris",
            "wrong_answers": ["Londres", "Berlin", "Madrid"]
        },
        {
            "text": "Qui a peint la Joconde ?",
            "category": "Art",
            "difficulty": Difficulty.EASY,
            "points": 2,
            "correct_answer": "Léonard de Vinci",
            "wrong_answers": ["Michel-Ange", "Raphaël", "Van Gogh"]
        },
        {
            "text": "Combien de continents y a-t-il sur Terre ?",
            "category": "Géographie",
            "difficulty": Difficulty.EASY,
            "points": 2,
            "correct_answer": "7",
            "wrong_answers": ["5", "6", "8"]
        },
        
        # Questions moyennes (4 points)
        {
            "text": "Quel est le plus grand océan du monde ?",
            "category": "Géographie",
            "difficulty": Difficulty.MEDIUM,
            "points": 4,
            "correct_answer": "Océan Pacifique",
            "wrong_answers": ["Océan Atlantique", "Océan Indien", "Océan Arctique"]
        },
        {
            "text": "En quelle année a eu lieu la Révolution française ?",
            "category": "Histoire",
            "difficulty": Difficulty.MEDIUM,
            "points": 4,
            "correct_answer": "1789",
            "wrong_answers": ["1776", "1792", "1815"]
        },
        
        # Questions difficiles (6 points)
        {
            "text": "Quel philosophe a écrit 'Ainsi parlait Zarathoustra' ?",
            "category": "Philosophie",
            "difficulty": Difficulty.HARD,
            "points": 6,
            "correct_answer": "Friedrich Nietzsche",
            "wrong_answers": ["Platon", "Kant", "Descartes"]
        },
        {
            "text": "Quelle est la formule chimique de l'eau ?",
            "category": "Sciences",
            "difficulty": Difficulty.HARD,
            "points": 6,
            "correct_answer": "H₂O",
            "wrong_answers": ["CO₂", "NaCl", "C₆H₁₂O₆"]
        }
    ]
    
    for q_data in questions_data:
        question = Question(
            text=q_data["text"],
            category=q_data["category"],
            difficulty=q_data["difficulty"],
            points=q_data["points"],
            correct_answer=q_data["correct_answer"],
            wrong_answers=json.dumps(q_data["wrong_answers"])
        )
        db.add(question)
    
    db.commit()
    print(f"✅ {len(questions_data)} questions créées")

def seed_game_session(db: Session):
    """Créer une session de jeu de test"""
    
    # Créer la session de jeu
    game = GameSession(
        code="TEST123",
        current_round=RoundType.MANCHE_1,
        total_players=6,
        players_per_team=2
    )
    db.add(game)
    db.flush()  # Pour obtenir l'ID
    
    # Créer 3 équipes
    teams = []
    for i in range(3):
        team = Team(
            name=f"Équipe {i+1}",
            game_session_id=game.id,
            score=0
        )
        db.add(team)
        teams.append(team)
    
    db.flush()
    
    # Créer 2 joueurs par équipe
    player_names = [
        ["Alice", "Bob"],
        ["Charlie", "Diana"],
        ["Eve", "Frank"]
    ]
    
    for i, team in enumerate(teams):
        for j, name in enumerate(player_names[i]):
            player = Player(
                name=name,
                team_id=team.id
            )
            db.add(player)
    
    # Donner 3 jetons à chaque équipe
    token_types = [TokenType.SWAP, TokenType.PENALTY, TokenType.BONUS]
    for team in teams:
        for token_type in token_types:
            token = Token(
                team_id=team.id,
                token_type=token_type,
                is_used=False
            )
            db.add(token)
    
    db.commit()
    print("✅ Session de jeu de test créée avec 3 équipes et 6 joueurs")
    print(f"   Code de la partie: {game.code}")

def seed_round2_themes_and_questions(db: Session):
    """Peupler la base avec 10 thèmes et 10 questions par thème pour Round 2"""
    
    themes_data = [
        # Serious themes
        {
            "name": "Histoire de France",
            "category": ThemeCategory.SERIOUS,
            "difficulty_level": 5,
            "description": "Des Gaulois à la Ve République",
            "questions": [
                ("Quel roi a été surnommé le Roi-Soleil ?", "Louis XIV", ["Louis XVI", "Henri IV", "François Ier"]),
                ("En quelle année Napoléon a-t-il été sacré empereur ?", "1804", ["1799", "1806", "1812"]),
                ("Qui était le premier président de la Ve République ?", "Charles de Gaulle", ["Vincent Auriol", "René Coty", "Georges Pompidou"]),
                ("Quelle bataille a marqué la fin de Napoléon en 1815 ?", "Waterloo", ["Austerlitz", "Trafalgar", "Leipzig"]),
                ("Quel traité a mis fin à la Première Guerre mondiale ?", "Traité de Versailles", ["Traité de Paris", "Traité de Vienne", "Traité de Berlin"]),
                ("Qui a mené la résistance française pendant la Seconde Guerre mondiale ?", "Jean Moulin", ["Philippe Pétain", "Pierre Laval", "Henri Giraud"]),
                ("En quelle année la Bastille a-t-elle été prise ?", "1789", ["1790", "1788", "1791"]),
                ("Quel roi a signé l'Édit de Nantes ?", "Henri IV", ["Louis XIII", "François Ier", "Charles IX"]),
                ("Combien de républiques la France a-t-elle connues ?", "5", ["4", "6", "3"]),
                ("Quel événement a déclenché la Révolution de 1848 ?", "L'interdiction des banquets réformistes", ["La famine", "Une invasion étrangère", "Un coup d'état militaire"]),
            ]
        },
        {
            "name": "Sciences & Nature",
            "category": ThemeCategory.SERIOUS,
            "difficulty_level": 6,
            "description": "Physique, chimie, biologie et au-delà",
            "questions": [
                ("Quel est l'élément chimique le plus abondant dans l'univers ?", "Hydrogène", ["Hélium", "Oxygène", "Carbone"]),
                ("Combien d'os possède le corps humain adulte ?", "206", ["208", "204", "212"]),
                ("Quelle planète est la plus proche du Soleil ?", "Mercure", ["Vénus", "Mars", "Terre"]),
                ("Quel scientifique a formulé la théorie de la relativité ?", "Albert Einstein", ["Isaac Newton", "Niels Bohr", "Max Planck"]),
                ("Quel est le plus grand organe du corps humain ?", "La peau", ["Le foie", "Les poumons", "L'intestin"]),
                ("Quelle est la vitesse de la lumière en km/s ?", "300 000", ["150 000", "500 000", "1 000 000"]),
                ("Quel gaz représente environ 78% de l'atmosphère terrestre ?", "Azote", ["Oxygène", "Argon", "Dioxyde de carbone"]),
                ("Combien de chromosomes possède une cellule humaine normale ?", "46", ["44", "48", "42"]),
                ("Quel est l'animal terrestre le plus rapide ?", "Le guépard", ["Le lion", "L'antilope", "Le lévrier"]),
                ("Quelle est la température du zéro absolu en degrés Celsius ?", "-273,15", ["-200", "-300", "-250"]),
            ]
        },
        {
            "name": "Géographie mondiale",
            "category": ThemeCategory.SERIOUS,
            "difficulty_level": 4,
            "description": "Capitales, fleuves, montagnes et pays",
            "questions": [
                ("Quel est le plus long fleuve du monde ?", "Le Nil", ["L'Amazone", "Le Yangtsé", "Le Mississippi"]),
                ("Quelle est la capitale de l'Australie ?", "Canberra", ["Sydney", "Melbourne", "Brisbane"]),
                ("Quel est le plus petit pays du monde ?", "Le Vatican", ["Monaco", "Saint-Marin", "Liechtenstein"]),
                ("Sur quel continent se trouve le Kilimandjaro ?", "Afrique", ["Asie", "Amérique du Sud", "Europe"]),
                ("Quel détroit sépare l'Europe de l'Afrique ?", "Détroit de Gibraltar", ["Détroit du Bosphore", "Détroit de Malacca", "Détroit d'Ormuz"]),
                ("Quelle est la mer la plus salée du monde ?", "La mer Morte", ["La mer Rouge", "La mer Caspienne", "La mer Méditerranée"]),
                ("Combien de pays composent l'Union européenne (2024) ?", "27", ["28", "25", "30"]),
                ("Quel est le désert le plus grand du monde ?", "Le Sahara", ["Le Gobi", "L'Antarctique", "L'Arabie"]),
                ("Quelle est la montagne la plus haute du monde ?", "L'Everest", ["Le K2", "Le Kangchenjunga", "Le Lhotse"]),
                ("Dans quel pays se trouve le Machu Picchu ?", "Pérou", ["Bolivie", "Colombie", "Équateur"]),
            ]
        },
        # Pop Culture themes
        {
            "name": "Cinéma & Séries",
            "category": ThemeCategory.POP_CULTURE,
            "difficulty_level": 3,
            "description": "Blockbusters, classiques et binge-watching",
            "questions": [
                ("Qui réalise la trilogie Le Seigneur des Anneaux ?", "Peter Jackson", ["James Cameron", "Steven Spielberg", "Ridley Scott"]),
                ("Dans quelle série les personnages vivent à Westeros ?", "Game of Thrones", ["The Witcher", "Vikings", "Lord of the Rings"]),
                ("Quel acteur incarne Jack dans Titanic ?", "Leonardo DiCaprio", ["Brad Pitt", "Matt Damon", "Johnny Depp"]),
                ("Combien de films composent la saga Star Wars principale ?", "9", ["6", "8", "12"]),
                ("Quel studio a produit Toy Story ?", "Pixar", ["DreamWorks", "Disney Animation", "Illumination"]),
                ("Dans quel film entend-on 'I'll be back' ?", "Terminator", ["Die Hard", "Rambo", "Predator"]),
                ("Qui joue le rôle de Joker dans The Dark Knight ?", "Heath Ledger", ["Jack Nicholson", "Joaquin Phoenix", "Jared Leto"]),
                ("Quelle série Netflix parle d'un jeu de survie coréen ?", "Squid Game", ["Alice in Borderland", "The 8 Show", "Sweet Home"]),
                ("Combien de pierres d'infinité y a-t-il dans Marvel ?", "6", ["5", "7", "8"]),
                ("Quel réalisateur est connu pour Inception et Interstellar ?", "Christopher Nolan", ["Denis Villeneuve", "David Fincher", "Quentin Tarantino"]),
            ]
        },
        {
            "name": "Musique Pop & Rock",
            "category": ThemeCategory.POP_CULTURE,
            "difficulty_level": 4,
            "description": "Des Beatles aux artistes d'aujourd'hui",
            "questions": [
                ("Quel groupe a chanté 'Bohemian Rhapsody' ?", "Queen", ["Led Zeppelin", "Pink Floyd", "The Rolling Stones"]),
                ("Comment s'appelle le chanteur de U2 ?", "Bono", ["The Edge", "Sting", "Morrissey"]),
                ("Quel artiste est surnommé 'The King of Pop' ?", "Michael Jackson", ["Elvis Presley", "Prince", "James Brown"]),
                ("Combien de membres comptait le groupe Beatles ?", "4", ["3", "5", "6"]),
                ("Quel album de Pink Floyd représente un prisme sur sa pochette ?", "The Dark Side of the Moon", ["The Wall", "Wish You Were Here", "Animals"]),
                ("Quelle chanteuse a interprété 'Rolling in the Deep' ?", "Adele", ["Amy Winehouse", "Beyoncé", "Rihanna"]),
                ("Quel festival français de musique se tient à Carhaix ?", "Les Vieilles Charrues", ["Les Eurockéennes", "Rock en Seine", "Hellfest"]),
                ("De quel pays vient le groupe ABBA ?", "Suède", ["Norvège", "Danemark", "Finlande"]),
                ("Quel rappeur français a sorti l'album 'Civilisation' ?", "Orelsan", ["Nekfeu", "Booba", "PNL"]),
                ("Quel instrument joue Jimi Hendrix ?", "Guitare", ["Basse", "Batterie", "Piano"]),
            ]
        },
        {
            "name": "Jeux Vidéo",
            "category": ThemeCategory.POP_CULTURE,
            "difficulty_level": 5,
            "description": "De Pong à l'eSport moderne",
            "questions": [
                ("Quel est le jeu vidéo le plus vendu de tous les temps ?", "Minecraft", ["GTA V", "Tetris", "Wii Sports"]),
                ("Comment s'appelle le personnage principal de Zelda ?", "Link", ["Zelda", "Ganondorf", "Epona"]),
                ("Quel studio développe les jeux Pokémon ?", "Game Freak", ["Nintendo", "HAL Laboratory", "Creatures Inc."]),
                ("En quelle année est sorti le premier Super Mario Bros ?", "1985", ["1983", "1987", "1990"]),
                ("Quel jeu de battle royale a popularisé le genre en 2017 ?", "Fortnite", ["PUBG", "Apex Legends", "Call of Duty Warzone"]),
                ("Quelle entreprise fabrique la PlayStation ?", "Sony", ["Microsoft", "Nintendo", "Sega"]),
                ("Dans quel jeu explore-t-on la ville de Night City ?", "Cyberpunk 2077", ["Watch Dogs", "Deus Ex", "GTA VI"]),
                ("Quel est le vrai nom de Master Chief dans Halo ?", "John-117", ["Marcus Fenix", "Sam Fisher", "Commander Shepard"]),
                ("Quel jeu de From Software est sorti en 2022 ?", "Elden Ring", ["Sekiro", "Dark Souls 4", "Bloodborne 2"]),
                ("Combien de joueurs maximum dans une partie de League of Legends ?", "10", ["8", "12", "6"]),
            ]
        },
        {
            "name": "Sport & Compétition",
            "category": ThemeCategory.POP_CULTURE,
            "difficulty_level": 4,
            "description": "Football, JO, records et légendes",
            "questions": [
                ("Combien de joueurs composent une équipe de football ?", "11", ["10", "12", "9"]),
                ("Quel pays a remporté la Coupe du Monde 2022 ?", "Argentine", ["France", "Brésil", "Allemagne"]),
                ("Dans quel sport utilise-t-on un volant ?", "Badminton", ["Tennis", "Ping-pong", "Squash"]),
                ("Combien de sets faut-il gagner pour remporter un match de tennis en Grand Chelem (hommes) ?", "3", ["2", "4", "5"]),
                ("Quel nageur détient le record de médailles d'or olympiques ?", "Michael Phelps", ["Mark Spitz", "Ryan Lochte", "Ian Thorpe"]),
                ("Dans quelle ville se sont déroulés les JO de 2024 ?", "Paris", ["Los Angeles", "Tokyo", "Londres"]),
                ("Quel sport pratique Tony Parker ?", "Basketball", ["Football", "Tennis", "Handball"]),
                ("Combien de tours compte le Tour de France en général ?", "21", ["18", "23", "25"]),
                ("Quel pays a inventé le rugby ?", "Angleterre", ["France", "Nouvelle-Zélande", "Australie"]),
                ("Qui est le meilleur buteur de l'histoire de la Ligue des Champions ?", "Cristiano Ronaldo", ["Lionel Messi", "Robert Lewandowski", "Raúl"]),
            ]
        },
        # Whimsical themes
        {
            "name": "Mythes & Légendes",
            "category": ThemeCategory.WHIMSICAL,
            "difficulty_level": 6,
            "description": "Dieux grecs, créatures fantastiques et épopées",
            "questions": [
                ("Qui est le roi des dieux dans la mythologie grecque ?", "Zeus", ["Poséidon", "Hadès", "Arès"]),
                ("Quel héros grec a tué la Méduse ?", "Persée", ["Héraclès", "Thésée", "Achille"]),
                ("Comment s'appelle le marteau de Thor ?", "Mjöllnir", ["Gungnir", "Excalibur", "Stormbreaker"]),
                ("Quel monstre garde le labyrinthe de Crète ?", "Le Minotaure", ["Le Sphinx", "Cerbère", "L'Hydre"]),
                ("Dans quelle mythologie trouve-t-on le Valhalla ?", "Nordique", ["Grecque", "Égyptienne", "Celtique"]),
                ("Qui est le dieu égyptien des morts ?", "Anubis", ["Osiris", "Râ", "Horus"]),
                ("Quel est le nom du cheval ailé de la mythologie grecque ?", "Pégase", ["Bucéphale", "Sleipnir", "Arion"]),
                ("Combien de travaux Héraclès a-t-il accomplis ?", "12", ["10", "7", "15"]),
                ("Quel animal est le phénix ?", "Un oiseau de feu", ["Un dragon", "Un serpent", "Un loup"]),
                ("Qui a ouvert la boîte contenant tous les maux du monde ?", "Pandore", ["Ève", "Athéna", "Cassandre"]),
            ]
        },
        {
            "name": "Gastronomie & Cuisine",
            "category": ThemeCategory.WHIMSICAL,
            "difficulty_level": 3,
            "description": "Plats, ingrédients et traditions culinaires",
            "questions": [
                ("De quel pays vient le sushi ?", "Japon", ["Chine", "Corée", "Thaïlande"]),
                ("Quel fromage est utilisé traditionnellement sur une pizza Margherita ?", "Mozzarella", ["Parmesan", "Cheddar", "Gruyère"]),
                ("Quel fruit est l'ingrédient principal du guacamole ?", "Avocat", ["Tomate", "Citron vert", "Mangue"]),
                ("Dans quel pays a été inventée la baguette ?", "France", ["Italie", "Allemagne", "Espagne"]),
                ("Quel est l'ingrédient principal du houmous ?", "Pois chiches", ["Lentilles", "Haricots blancs", "Fèves"]),
                ("Quelle épice donne sa couleur jaune au curry ?", "Curcuma", ["Safran", "Paprika", "Gingembre"]),
                ("De quel pays vient le kimchi ?", "Corée du Sud", ["Japon", "Chine", "Vietnam"]),
                ("Combien d'étoiles maximum un restaurant peut-il avoir au Guide Michelin ?", "3", ["4", "5", "2"]),
                ("Quel alcool est à la base d'un mojito ?", "Rhum", ["Vodka", "Tequila", "Gin"]),
                ("Quel plat italien signifie littéralement 'petites ficelles' ?", "Spaghetti", ["Linguine", "Tagliatelle", "Penne"]),
            ]
        },
        {
            "name": "Animaux Insolites",
            "category": ThemeCategory.WHIMSICAL,
            "difficulty_level": 5,
            "description": "Records, comportements bizarres et créatures étonnantes",
            "questions": [
                ("Quel animal peut dormir debout ?", "Le cheval", ["La vache", "Le mouton", "La chèvre"]),
                ("Combien de cœurs possède une pieuvre ?", "3", ["2", "4", "1"]),
                ("Quel est l'animal le plus bruyant de la planète ?", "La crevette-pistolet", ["La baleine bleue", "Le lion", "Le cachalot"]),
                ("Quel mammifère peut voler ?", "La chauve-souris", ["L'écureuil volant", "Le colibri", "Le phalanger volant"]),
                ("Combien de pattes a un homard ?", "10", ["8", "6", "12"]),
                ("Quel animal a les empreintes digitales les plus similaires à l'homme ?", "Le koala", ["Le chimpanzé", "Le gorille", "L'orang-outan"]),
                ("Quelle est la durée de gestation d'un éléphant en mois ?", "22", ["12", "18", "24"]),
                ("Quel oiseau ne peut pas voler mais court très vite ?", "L'autruche", ["Le pingouin", "Le kiwi", "Le dodo"]),
                ("Quel animal peut régénérer ses membres perdus ?", "L'axolotl", ["Le lézard", "L'étoile de mer", "Le crabe"]),
                ("Combien d'yeux a une araignée en général ?", "8", ["6", "4", "10"]),
            ]
        },
    ]
    
    theme_count = 0
    question_count = 0
    
    for theme_data in themes_data:
        theme = Theme(
            name=theme_data["name"],
            category=theme_data["category"],
            difficulty_level=theme_data["difficulty_level"],
            description=theme_data["description"]
        )
        db.add(theme)
        db.flush()  # Pour obtenir l'ID du thème
        
        theme_count += 1
        
        # Créer les 10 questions pour ce thème
        for i, (text, correct, wrong) in enumerate(theme_data["questions"], start=1):
            # Difficulté progressive: question_number = difficulty
            if i <= 3:
                difficulty = Difficulty.EASY
                points = 2
            elif i <= 7:
                difficulty = Difficulty.MEDIUM
                points = 4
            else:
                difficulty = Difficulty.HARD
                points = 6
            
            question = Question(
                text=text,
                category=theme_data["category"].value if hasattr(theme_data["category"], 'value') else theme_data["name"],
                difficulty=difficulty,
                points=points,
                correct_answer=correct,
                wrong_answers=json.dumps(wrong),
                theme_id=theme.id,
                question_number=i
            )
            db.add(question)
            question_count += 1
    
    db.commit()
    print(f"✅ {theme_count} thèmes Round 2 créés avec {question_count} questions")


def seed_round2_game_session(db: Session):
    """Créer une session de jeu de test pour Round 2 (16 joueurs individuels)"""
    
    # Créer la session de jeu Round 2
    game = GameSession(
        code="ROUND2",
        current_round=RoundType.MANCHE_2,
        total_players=16,
        players_per_team=1
    )
    db.add(game)
    db.flush()
    
    # Créer une équipe "conteneur" pour les joueurs individuels
    team = Team(
        name="Round 2 Players",
        game_session_id=game.id,
        score=0
    )
    db.add(team)
    db.flush()
    
    # Créer 16 joueurs individuels
    player_names = [
        "Alice", "Bob", "Charlie", "Diana", "Eve", "Frank",
        "Grace", "Henri", "Iris", "Julien", "Karine", "Lucas",
        "Marie", "Nicolas", "Olivia", "Paul"
    ]
    
    for name in player_names:
        player = Player(
            name=name,
            team_id=team.id
        )
        db.add(player)
    
    db.commit()
    print(f"✅ Session Round 2 créée avec 16 joueurs (code: ROUND2)")


def main():
    """Fonction principale"""
    db = SessionLocal()
    
    try:
        print("🧪 Début du peuplement de la base de données...")
        
        # Vider les tables existantes (pour les tests)
        db.query(PlayerRound2Stats).delete()
        db.query(Token).delete()
        db.query(Player).delete()
        db.query(Team).delete()
        db.query(GameSession).delete()
        db.query(Question).delete()
        db.query(Theme).delete()
        db.commit()
        
        # Peupler les données
        seed_questions(db)
        seed_game_session(db)
        seed_round2_themes_and_questions(db)
        seed_round2_game_session(db)
        
        print("\n🎉 Base de données peuplée avec succès !")
        print("\n📊 Données créées:")
        print(f"   - Questions: {db.query(Question).count()}")
        print(f"   - Thèmes Round 2: {db.query(Theme).count()}")
        print(f"   - Sessions de jeu: {db.query(GameSession).count()}")
        print(f"   - Équipes: {db.query(Team).count()}")
        print(f"   - Joueurs: {db.query(Player).count()}")
        print(f"   - Jetons: {db.query(Token).count()}")
        print(f"\n🎮 Codes de sessions disponibles:")
        print(f"   - TEST123 (Round 1, 3 équipes)")
        print(f"   - ROUND2 (Round 2, 16 joueurs)")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Erreur lors du peuplement: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()