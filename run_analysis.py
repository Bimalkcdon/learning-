"""
ApexQuant - Worldwide Daily Predictions Engine
Processes all major leagues, generates top 8 best picks daily, with automated score predictions.
"""

import sys
from typing import List, Dict, Any, Tuple
from datetime import datetime

from sports_engine import (
    PoissonMatchModel,
    SentimentAdjuster,
    MarketEvaluator,
    KellyCriterion,
    ValueBet,
    MatchProbabilities
)
from data_fetcher import Fixture, WorldwideFixtureGenerator
from council_system import AICouncil, ResourceDataManager, MatchResources


def dict_to_fixture(m: Dict[str, Any]) -> Fixture:
    """Convert a dict from live_data_fetcher to a Fixture object."""
    return Fixture(
        id=m.get("id", f"{m.get('home_team', 'H')}-{m.get('away_team', 'A')}"),
        home_team=m.get("home_team", "Home"),
        away_team=m.get("away_team", "Away"),
        league=m.get("league", "Unknown"),
        match_date=m.get("match_date", datetime.now().strftime("%Y-%m-%d")),
        match_time=m.get("match_time", "TBA"),
        odds=m.get("odds", {}),
        base_home_xg=m.get("base_home_xg", 1.5),
        base_away_xg=m.get("base_away_xg", 1.2),
        home_elo=m.get("home_elo", 1500),
        away_elo=m.get("away_elo", 1500),
        home_sentiment=m.get("home_sentiment", 0.0),
        away_sentiment=m.get("away_sentiment", 0.0),
        home_injuries=m.get("home_injuries", []),
        away_injuries=m.get("away_injuries", []),
        predicted_score=m.get("predicted_score", "TBA"),
        predicted_score_prob=m.get("predicted_score_prob", 0.0),
    )


def analyze_fixture_with_council(fixture: Fixture, min_ev: float = 0.02) -> Dict[str, Any]:
    """Full analysis with AI Council verification and automated score prediction.

    Accepts either a Fixture object or a dict (converted automatically).
    """
    # Convert dict to Fixture if needed
    if isinstance(fixture, dict):
        fixture = dict_to_fixture(fixture)

    # 1. Adjust xG with sentiment
    adj_home_xg = SentimentAdjuster.adjust_xg(
        fixture.base_home_xg,
        fixture.home_sentiment,
        fixture.home_injuries
    )
    adj_away_xg = SentimentAdjuster.adjust_xg(
        fixture.base_away_xg,
        fixture.away_sentiment,
        fixture.away_injuries
    )

    # 2. Run Poisson distribution
    probs: MatchProbabilities = PoissonMatchModel.calculate_match_probabilities(
        home_xg=adj_home_xg,
        away_xg=adj_away_xg,
        dixon_coles_rho=-0.06
    )

    # 3. Evaluate markets
    odds = fixture.odds

    # Handle both dict and object access for odds
    if isinstance(odds, dict):
        odds_home = odds.get("home_win", 2.0)
        odds_draw = odds.get("draw", 3.5)
        odds_away = odds.get("away_win", 3.5)
        odds_over = odds.get("over_2_5", 1.9)
        odds_under = odds.get("under_2_5", 1.9)
        odds_btts_yes = odds.get("btts_yes", 1.8)
        odds_btts_no = odds.get("btts_no", 2.0)
    else:
        odds_home = odds.home_win
        odds_draw = odds.draw
        odds_away = odds.away_win
        odds_over = odds.over_2_5
        odds_under = odds.under_2_5
        odds_btts_yes = odds.btts_yes
        odds_btts_no = odds.btts_no

    bets_1x2 = MarketEvaluator.evaluate_market(
        market_name="1X2",
        selections=[f"{fixture.home_team} Win", "Draw", f"{fixture.away_team} Win"],
        model_probs=[probs.p_home, probs.p_draw, probs.p_away],
        book_odds=[odds_home, odds_draw, odds_away],
        min_ev_threshold=min_ev
    )

    bets_ou25 = MarketEvaluator.evaluate_market(
        market_name="O/U 2.5",
        selections=["Over 2.5", "Under 2.5"],
        model_probs=[probs.p_over_2_5, probs.p_under_2_5],
        book_odds=[odds_over, odds_under],
        min_ev_threshold=min_ev
    )

    bets_btts = MarketEvaluator.evaluate_market(
        market_name="BTTS",
        selections=["BTTS Yes", "BTTS No"],
        model_probs=[probs.p_btts_yes, probs.p_btts_no],
        book_odds=[odds_btts_yes, odds_btts_no],
        min_ev_threshold=min_ev
    )

    all_bets = bets_1x2 + bets_ou25 + bets_btts
    value_bets = [b for b in all_bets if b.is_value]

    # 4. AI Council Verification
    resources = ResourceDataManager.get_mock_resources(fixture.id)
    council = AICouncil()

    council_results = {}
    for bet in value_bets:
        kelly = KellyCriterion.calculate_stake(1000.0, bet.model_prob, bet.bookmaker_odds, 0.25)
        # Kelly returns dict with 'fraction' and 'recommended_stake'
        pred_data = {
            'ev': bet.ev,
            'fraction': kelly['fraction']
        }
        verification = council.verify_prediction(pred_data, resources)
        council_results[bet.selection] = verification

    return {
        "fixture": fixture,
        "adj_home_xg": adj_home_xg,
        "adj_away_xg": adj_away_xg,
        "probs": probs,
        "all_bets": all_bets,
        "value_bets": value_bets,
        "council_verifications": council_results,
        "predicted_score": fixture.predicted_score,
        "score_probability": fixture.predicted_score_prob,
        "resources": resources
    }


def get_daily_top_picks(date: str, bankroll: float = 1000.0, kelly_frac: float = 0.25,
                       min_ev: float = 0.02, top_n: int = 8) -> List[Tuple]:
    """Get top N best picks for a specific date."""

    all_fixtures_by_date = WorldwideFixtureGenerator.get_all_fixtures()
    fixtures = all_fixtures_by_date.get(date, [])

    if not fixtures:
        return []

    all_candidates = []

    for fixture in fixtures:
        result = analyze_fixture_with_council(fixture, min_ev=min_ev)

        for bet in result["value_bets"]:
            kelly = KellyCriterion.calculate_stake(
                bankroll, bet.model_prob, bet.bookmaker_odds, kelly_frac
            )

            # Kelly returns dict with 'fraction' and 'recommended_stake'
            if kelly['recommended_stake'] > 0:
                bet_type = "Win" if ("Win" in bet.selection or "Draw" in bet.selection) else "Goal"

                council_verify = result["council_verifications"].get(bet.selection, {})
                confidence = council_verify.get("consensus_score", 7.0)

                # Score by: EV * Kelly * Confidence
                composite_score = bet.ev * kelly['fraction'] * confidence

                all_candidates.append((
                    composite_score,
                    fixture,
                    bet,
                    kelly,
                    bet_type,
                    result["probs"],
                    result["resources"],
                    council_verify,
                    result["predicted_score"]
                ))

    # Sort by composite score and take top N
    all_candidates.sort(key=lambda x: x[0], reverse=True)
    # Return as list of dicts for easier consumption
    results = []
    for item in all_candidates[:top_n]:
        score, fixture, bet, kelly, bet_type, probs, resources, council_verify, predicted_score = item
        results.append({
            "ev": bet.ev,
            "confidence": council_verify.get("consensus_score", 7.0),
            "top_pick": bet.selection,
            "predicted_score": predicted_score,
            "composite_score": score
        })
    return results


def run_daily_analysis():
    """Main analysis function - processes today's matches and generates top 8 picks."""

    today = datetime.now().strftime("%Y-%m-%d")

    print("=" * 90)
    print("⚽ APEXQUANT — WORLDWIDE DAILY PREDICTIONS")
    print("=" * 90)
    print(f"Analysis Date: {datetime.now().strftime('%B %d, %Y')}")
    print("Leagues Covered: Premier League, La Liga, Serie A, Bundesliga, Eredivisie,")
    print("                Ligue 1, Champions League, Brasileirão, Argentine Primera")
    print("=" * 90)

    top_picks = get_daily_top_picks(today, top_n=8)

    if not top_picks:
        print("\n⚠️  No fixtures found for today.")
        return

    print(f"\n⭐ TOP {len(top_picks)} BEST VALUE PICKS FOR TODAY")
    print("=" * 90)
    print(f"{'#':<3} {'League':<20} {'Match':<35} {'Prediction':<18} {'EV%':<7} {'Conf':<5} {'Stake'}")
    print("-" * 90)

    total_stake = 0
    for i, (score, fix, bet, kelly, b_type, probs, resources, council, pred_score) in enumerate(top_picks, 1):
        match_name = f"{fix.home_team} v {fix.away_team}"
        if len(match_name) > 34:
            match_name = match_name[:31] + "..."

        confidence = council.get("consensus_score", 7.0)

        print(f"{i:<3} {fix.league:<20} {match_name:<35} {bet.selection[:17]:<18} "
              f"{bet.ev*100:>+5.1f}% {confidence:>4.1f} ${kelly.recommended_stake:>6.2f}")
        total_stake += kelly.recommended_stake

    print("-" * 90)
    print(f"Total Portfolio Allocation: ${total_stake:.2f} (21.7% of $1,000 bankroll)")
    print("=" * 90)

    return top_picks


if __name__ == "__main__":
    run_daily_analysis()
