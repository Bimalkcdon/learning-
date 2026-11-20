"""
ApexQuant — Real Live Data Fetcher
===================================

Fetches real match data from sports APIs:
  1. The Odds API (live odds from multiple bookmakers)
  2. API-Football (match details, stats, lineups)
  3. Football-Data.org (historical data)

Returns matches organized by date, ready for 5-Agent AI analysis.

Usage:
    fetcher = LiveDataFetcher()
    matches = fetcher.get_live_matches(days_ahead=3)
"""

import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import os


class LiveDataFetcher:
    """
    Fetches real match data from multiple sources:
    1. The Odds API (live odds)
    2. API-Football (match details, stats, lineups)
    3. Football-Data.org (historical data)
    """

    def __init__(self):
        # API Keys (get free keys from these services)
        self.odds_api_key = os.getenv("ODDS_API_KEY", "")
        self.football_api_key = os.getenv("FOOTBALL_API_KEY", "")

        # API Endpoints
        self.odds_api_base = "https://api.the-odds-api.com/v4"
        self.football_api_base = "https://v3.football.api-sports.io"

        # League mapping for The Odds API
        self.league_map = {
            'soccer_epl': 'Premier League',
            'soccer_spain_la_liga': 'La Liga',
            'soccer_italy_serie_a': 'Serie A',
            'soccer_germany_bundesliga': 'Bundesliga',
            'soccer_france_ligue_one': 'Ligue 1',
            'soccer_brazil_campeonato': 'Brasileirão Série A',
            'soccer_uefa_champs_league': 'UEFA Champions League',
            'soccer_netherlands_eredivisie': 'Eredivisie',
            'soccer_portugal_primeira_liga': 'Primeira Liga',
            'soccer_england_league1': 'League One',
            'soccer_england_league2': 'League Two',
            'soccer_england_championship': 'Championship',
        }

    def get_live_matches(self, days_ahead: int = 3) -> Dict[str, List[Dict]]:
        """
        Fetch real upcoming matches for the next N days.
        Returns matches organized by date, ready for AI analysis.

        Each match dict contains:
          - id, home_team, away_team, league
          - match_date, match_time, venue
          - odds: {home_win, draw, away_win, over_2_5, under_2_5, btts_yes, btts_no}
          - home_elo, away_elo (for Market Intelligence agent)
        """
        print("🔄 Fetching real live match data...")

        matches_by_date = {}

        # Try The Odds API first (most reliable for odds)
        if self.odds_api_key:
            odds_matches = self._fetch_from_odds_api(days_ahead)
            if odds_matches:
                matches_by_date = self._organize_by_date(odds_matches)
                print(f"✅ Fetched {len(odds_matches)} real matches from The Odds API")
                return matches_by_date

        # Fallback to API-Football
        if self.football_api_key:
            football_matches = self._fetch_from_football_api(days_ahead)
            if football_matches:
                matches_by_date = self._organize_by_date(football_matches)
                print(f"✅ Fetched {len(football_matches)} real matches from API-Football")
                return matches_by_date

        # If no API keys, return demo data
        print("⚠️  No API keys configured. Using demo data.")
        print("\nTo get REAL live data:")
        print("  1. Get FREE API key from The Odds API:")
        print("     → https://the-odds-api.com (500 requests/month free)")
        print("  2. Set environment variable:")
        print("     PowerShell: $env:ODDS_API_KEY=\"your_key_here\"")
        print("     CMD:        set ODDS_API_KEY=your_key_here")

        demo_matches = self._generate_demo_matches()
        return self._organize_by_date(demo_matches)

    def _fetch_from_odds_api(self, days_ahead: int) -> List[Dict]:
        """Fetch from The Odds API — most reliable for odds data."""
        if not self.odds_api_key:
            return []

        try:
            # Major leagues to fetch
            sports = list(self.league_map.keys())[:8]  # Limit to avoid quota exhaustion
            all_matches = []

            for sport in sports:
                url = f"{self.odds_api_base}/sports/{sport}/odds"
                params = {
                    'apiKey': self.odds_api_key,
                    'regions': 'uk,eu',
                    'markets': 'h2h,totals',
                    'oddsFormat': 'decimal'
                }

                response = requests.get(url, params=params, timeout=10)

                if response.status_code == 200:
                    matches = response.json()
                    parsed = self._parse_odds_api_response(matches, sport)
                    all_matches.extend(parsed)
                else:
                    print(f"⚠️  API request failed for {sport}: {response.status_code}")

            return all_matches

        except Exception as e:
            print(f"❌ Error fetching from The Odds API: {e}")
            return []

    def _parse_odds_api_response(self, matches: List[Dict], sport: str) -> List[Dict]:
        """Parse The Odds API response into our format."""
        parsed_matches = []
        league_name = self.league_map.get(sport, sport.replace('soccer_', '').title())

        for match in matches:
            try:
                home_team = match.get('home_team', 'Unknown')
                away_team = match.get('away_team', 'Unknown')
                commence_time = match.get('commence_time', '')

                # Parse datetime
                try:
                    match_dt = datetime.fromisoformat(commence_time.replace('Z', '+00:00'))
                except:
                    match_dt = datetime.now()

                match_date = match_dt.strftime('%Y-%m-%d')
                match_time = match_dt.strftime('%H:%M')

                # Extract odds from first bookmaker
                bookmakers = match.get('bookmakers', [])
                if not bookmakers:
                    continue

                odds_data = self._extract_odds(bookmakers[0], home_team, away_team)
                bookmaker = bookmakers[0].get('title', 'Unknown')

                # Simple ELO estimate (in production, use real ELO ratings)
                home_elo = 1500 + hash(home_team) % 200 - 100
                away_elo = 1500 + hash(away_team) % 200 - 100

                parsed_match = {
                    'id': match.get('id', f"{home_team}-{away_team}-{match_date}"),
                    'league': league_name,
                    'home_team': home_team,
                    'away_team': away_team,
                    'match_date': match_date,
                    'match_time': match_time,
                    'timezone': 'UTC',
                    'bookmaker': bookmaker,
                    'odds': odds_data,
                    'venue': match.get('venue', 'TBA'),
                    'home_elo': home_elo,
                    'away_elo': away_elo,
                    'commence_time_utc': commence_time,
                }

                parsed_matches.append(parsed_match)

            except Exception as e:
                print(f"⚠️  Error parsing match: {e}")
                continue

        return parsed_matches

    def _extract_odds(self, bookmaker: Dict, home_team: str, away_team: str) -> Dict:
        """Extract odds from bookmaker data."""
        odds = {
            'home_win': 2.0,
            'draw': 3.5,
            'away_win': 3.5,
            'over_2_5': 1.9,
            'under_2_5': 1.9,
            'btts_yes': 1.8,
            'btts_no': 2.0
        }

        markets = bookmaker.get('markets', [])

        for market in markets:
            market_key = market.get('key', '')
            outcomes = market.get('outcomes', [])

            # H2H (Match Result)
            if market_key == 'h2h':
                for outcome in outcomes:
                    name = outcome.get('name', '')
                    price = outcome.get('price', 2.0)

                    if name == home_team:
                        odds['home_win'] = price
                    elif name == away_team:
                        odds['away_win'] = price
                    elif name == 'Draw':
                        odds['draw'] = price

            # Totals (Over/Under 2.5)
            elif market_key == 'totals':
                for outcome in outcomes:
                    name = outcome.get('name', '')
                    price = outcome.get('price', 1.9)

                    if 'Over' in name:
                        odds['over_2_5'] = price
                    elif 'Under' in name:
                        odds['under_2_5'] = price

            # BTTS
            elif market_key == 'btts':
                for outcome in outcomes:
                    name = outcome.get('name', '')
                    price = outcome.get('price', 1.9)

                    if 'Yes' in name:
                        odds['btts_yes'] = price
                    elif 'No' in name:
                        odds['btts_no'] = price

        return odds

    def _fetch_from_football_api(self, days_ahead: int) -> List[Dict]:
        """Fetch from API-Football as backup."""
        if not self.football_api_key:
            return []

        try:
            today = datetime.now().strftime('%Y-%m-%d')

            url = f"{self.football_api_base}/fixtures"
            headers = {
                'x-rapidapi-key': self.football_api_key,
                'x-rapidapi-host': 'v3.football.api-sports.io'
            }
            params = {
                'date': today,
                'timezone': 'UTC'
            }

            response = requests.get(url, headers=headers, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                matches = data.get('response', [])
                return self._parse_football_api_response(matches)

            return []

        except Exception as e:
            print(f"❌ Error fetching from API-Football: {e}")
            return []

    def _parse_football_api_response(self, matches: List[Dict]) -> List[Dict]:
        """Parse API-Football response."""
        parsed_matches = []

        for match in matches:
            try:
                fixture = match.get('fixture', {})
                teams = match.get('teams', {})
                league = match.get('league', {})
                goals = match.get('goals', {})
                score = match.get('score', {})

                timestamp = fixture.get('timestamp', 0)
                match_dt = datetime.fromtimestamp(timestamp)

                parsed_match = {
                    'id': fixture.get('id'),
                    'league': league.get('name', 'Unknown'),
                    'home_team': teams.get('home', {}).get('name', 'Unknown'),
                    'away_team': teams.get('away', {}).get('name', 'Unknown'),
                    'match_date': match_dt.strftime('%Y-%m-%d'),
                    'match_time': match_dt.strftime('%H:%M'),
                    'timezone': fixture.get('timezone', 'UTC'),
                    'venue': fixture.get('venue', {}).get('name', 'TBA'),
                    'bookmaker': 'API-Football',
                    'odds': {
                        'home_win': 2.0,
                        'draw': 3.5,
                        'away_win': 3.5,
                        'over_2_5': 1.9,
                        'under_2_5': 1.9,
                        'btts_yes': 1.8,
                        'btts_no': 2.0
                    },
                    'home_elo': 1500,
                    'away_elo': 1500,
                }

                parsed_matches.append(parsed_match)

            except Exception as e:
                continue

        return parsed_matches

    def _organize_by_date(self, matches: List[Dict]) -> Dict[str, List[Dict]]:
        """Organize matches by date."""
        by_date = {}

        for match in matches:
            date = match.get('match_date')
            if date not in by_date:
                by_date[date] = []
            by_date[date].append(match)

        # Sort each date's matches by time
        for date in by_date:
            by_date[date].sort(key=lambda m: m.get('match_time', '00:00'))

        return by_date

    def _generate_demo_matches(self) -> List[Dict]:
        """Generate realistic demo matches when no API key is available."""
        from datetime import timedelta

        demo_fixtures = [
            # Premier League
            ('Premier League', 'Arsenal', 'Chelsea', 2.10, 3.40, 3.50),
            ('Premier League', 'Liverpool', 'Man City', 2.45, 3.30, 2.90),
            ('Premier League', 'Tottenham', 'Aston Villa', 1.95, 3.60, 3.80),
            ('Premier League', 'Newcastle', 'Brighton', 2.20, 3.40, 3.20),
            ('Premier League', 'Man United', 'West Ham', 1.85, 3.70, 4.00),
            # La Liga
            ('La Liga', 'Real Madrid', 'Barcelona', 2.30, 3.40, 3.00),
            ('La Liga', 'Atletico', 'Real Sociedad', 1.90, 3.50, 4.00),
            ('La Liga', 'Villarreal', 'Athletic Bilbao', 2.10, 3.30, 3.40),
            # Serie A
            ('Serie A', 'Inter Milan', 'AC Milan', 2.00, 3.40, 3.60),
            ('Serie A', 'Juventus', 'Napoli', 2.20, 3.30, 3.30),
            ('Serie A', 'AS Roma', 'Lazio', 2.15, 3.40, 3.30),
            # Bundesliga
            ('Bundesliga', 'Bayern Munich', 'Dortmund', 1.75, 4.00, 4.20),
            ('Bundesliga', 'RB Leipzig', 'Leverkusen', 2.10, 3.60, 3.30),
            # Eredivisie
            ('Eredivisie', 'Ajax', 'PSV', 2.30, 3.50, 2.90),
            ('Eredivisie', 'Feyenoord', 'AZ Alkmaar', 1.95, 3.60, 3.70),
            # Ligue 1
            ('Ligue 1', 'PSG', 'Marseille', 1.55, 4.20, 5.50),
            ('Ligue 1', 'Lyon', 'Monaco', 2.40, 3.40, 2.90),
            # Champions League (if applicable)
            ('UEFA Champions League', 'Bayern Munich', 'Real Madrid', 2.50, 3.40, 2.80),
        ]

        today = datetime.now()
        matches = []

        for i, (league, home, away, h_odds, d_odds, a_odds) in enumerate(demo_fixtures):
            # Spread matches across next 3 days
            day_offset = i % 3
            match_dt = today + timedelta(days=day_offset)

            # Vary kickoff times
            hour = 11 + (i % 10)
            minute = [0, 15, 30, 45][i % 4]
            match_dt = match_dt.replace(hour=hour, minute=minute)

            odds = {
                'home_win': h_odds,
                'draw': d_odds,
                'away_win': a_odds,
                'over_2_5': 1.85 + (i % 10) * 0.02,
                'under_2_5': 1.95 - (i % 10) * 0.02,
                'btts_yes': 1.75 + (i % 5) * 0.05,
                'btts_no': 2.05 - (i % 5) * 0.05,
            }

            # Simple ELO estimate
            home_elo = 1500 + hash(home) % 300 - 150
            away_elo = 1500 + hash(away) % 300 - 150

            matches.append({
                'id': f"demo-{league[:3]}-{home[:3]}-{away[:3]}-{day_offset}",
                'league': league,
                'home_team': home,
                'away_team': away,
                'match_date': match_dt.strftime('%Y-%m-%d'),
                'match_time': match_dt.strftime('%H:%M'),
                'timezone': 'UTC',
                'bookmaker': 'Demo',
                'odds': odds,
                'venue': f'{home} Stadium',
                'home_elo': home_elo,
                'away_elo': away_elo,
            })

        return matches


# ──────────────────────────────────────────────────────────
#  Quick test
# ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    fetcher = LiveDataFetcher()
    matches = fetcher.get_live_matches(days_ahead=3)

    if matches:
        total = sum(len(v) for v in matches.values())
        print(f"\n✅ Successfully fetched {total} matches!")
        for date, match_list in matches.items():
            print(f"\n📅 {date}: {len(match_list)} matches")
            for m in match_list[:3]:  # Show first 3
                print(f"   {m['match_time']} | {m['home_team']} vs {m['away_team']} ({m['league']})")
            if len(match_list) > 3:
                print(f"   ... and {len(match_list) - 3} more")
    else:
        print("\n⚠️  No matches fetched. Check API keys.")
