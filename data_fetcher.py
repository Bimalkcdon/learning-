"""
ApexQuant — Data Fetcher (Stub Module)
Provides WorldwideFixtureGenerator and Fixture data structures.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
from datetime import datetime, timedelta
import random


@dataclass
class Fixture:
    """Represents a single football fixture/match."""
    id: str
    home_team: str
    away_team: str
    league: str
    match_date: str
    match_time: str
    odds: dict
    base_home_xg: float = 1.5
    base_away_xg: float = 1.2
    home_elo: int = 1500
    away_elo: int = 1500
    home_sentiment: float = 0.0
    away_sentiment: float = 0.0
    home_injuries: list = None
    away_injuries: list = None
    predicted_score: str = "TBA"
    predicted_score_prob: float = 0.0


class WorldwideFixtureGenerator:
    """Generates fixture data for all major leagues worldwide."""

    # Team lists for each league
    LEAGUES = {
        "Premier League": ["Arsenal", "Chelsea", "Liverpool", "Man City", "Tottenham", "Newcastle",
                          "Man United", "West Ham", "Brighton", "Aston Villa"],
        "La Liga": ["Real Madrid", "Barcelona", "Atletico Madrid", "Real Sociedad", "Villarreal",
                     "Athletic Bilbao", "Sevilla", "Betis"],
        "Serie A": ["Inter Milan", "AC Milan", "Juventus", "Napoli", "AS Roma", "Lazio",
                     "Fiorentina", "Verona"],
        "Bundesliga": ["Bayern Munich", "Borussia Dortmund", "RB Leipzig", "Leverkusen",
                        "Stuttgart", "Freiburg", "Mainz", "Wolfsburg"],
        "Eredivisie": ["Ajax", "PSV Eindhoven", "Feyenoord", "AZ Alkmaar", "Twente",
                        "Utrecht", "Eintracht Frankfurt", "Nijmegen"],
        "Ligue 1": ["PSG", "Marseille", "Lyon", "Monaco", "Lille", "Nice",
                     "Rennes", "Monaco"],
    }

    @classmethod
    def get_all_fixtures(cls) -> Dict[str, List[Fixture]]:
        """Get all fixtures organized by date."""
        today = datetime.now()
        by_date = {}

        # Generate fixtures for next 3 days
        for day_offset in range(3):
            date = (today + timedelta(days=day_offset)).strftime("%Y-%m-%d")
            fixtures = cls._generate_fixtures_for_date(date, day_offset)
            by_date[date] = fixtures

        return by_date

    @classmethod
    def _generate_fixtures_for_date(cls, date_str: str, day_offset: int) -> List[Fixture]:
        """Generate a set of fixtures for a specific date."""
        fixtures = []
        leagues = cls.LEAGUES

        # Pick 3-4 random leagues for this date
        selected_leagues = random.sample(list(leagues.keys()), k=min(4, len(leagues)))

        for league in selected_leagues:
            home_teams = leagues[league]
            # Generate 2-3 fixtures per league
            num_fixtures = random.randint(2, 3)

            for _ in range(num_fixtures):
                home = random.choice(home_teams)
                away = random.choice([t for t in home_teams if t != home])

                # Generate match time
                hour = 14 + day_offset * 3 + random.randint(0, 4)
                minute = random.choice([0, 15, 30, 45])
                match_time = f"{hour:02d}:{minute:02d}"

                # Generate realistic odds
                from sports_engine import predict_poisson
                prediction = predict_poisson(home, away)

                odds = {
                    "home_win": round(1.0 / prediction["home_win_prob"] + random.uniform(-0.1, 0.1), 2),
                    "draw": round(1.0 / prediction["draw_prob"] + random.uniform(-0.1, 0.1), 2),
                    "away_win": round(1.0 / prediction["away_win_prob"] + random.uniform(-0.1, 0.1), 2),
                    "over_2_5": round(random.uniform(1.75, 2.05), 2),
                    "under_2_5": round(random.uniform(1.85, 2.15), 2),
                    "btts_yes": round(random.uniform(1.70, 1.90), 2),
                    "btts_no": round(random.uniform(2.00, 2.30), 2),
                }

                # Generate fixture
                fixture = Fixture(
                    id=f"{league.lower().replace(' ', '-')}-{home.replace(' ', '-')}-{away.replace(' ', '-')}-{day_offset}",
                    home_team=home,
                    away_team=away,
                    league=league,
                    match_date=date_str,
                    match_time=match_time,
                    odds=odds,
                    base_home_xg=prediction["predicted_home_goals"],
                    base_away_xg=prediction["predicted_away_goals"],
                    home_sentiment=round(random.uniform(-0.5, 0.5), 2),
                    away_sentiment=round(random.uniform(-0.5, 0.5), 2),
                    home_injuries=random.sample(["key_player", "suspended"], k=random.randint(0, 2)) if random.random() > 0.3 else [],
                    away_injuries=random.sample(["key_player", "suspended"], k=random.randint(0, 2)) if random.random() > 0.3 else [],
                )
                fixtures.append(fixture)

        # Sort by match time
        fixtures.sort(key=lambda f: f.match_time)
        return fixtures