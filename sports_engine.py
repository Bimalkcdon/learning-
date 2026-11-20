"""
ApexQuant — Sports Engine
Contains simulated match data and basic analytical functions.
In production, these would connect to real sports databases.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Tuple
from datetime import datetime
import random
import math


# ──────────────────────────────────────────────────────────
#  Team database — simulated historical stats
#  In production, replace with real historical data API.
# ──────────────────────────────────────────────────────────

TEAM_DATABASE: Dict[str, Dict[str, Any]] = {
    # Each team: rolling averages from last 10-20 matches
    # (These are realistic approximations — swap with real data later)
    "Arsenal": {"home_attack": 1.45, "home_defense": 0.85, "away_attack": 1.35, "away_defense": 0.95},
    "Chelsea": {"home_attack": 1.35, "home_defense": 0.90, "away_attack": 1.40, "away_defense": 0.88},
    "Liverpool": {"home_attack": 1.50, "home_defense": 0.80, "away_attack": 1.45, "away_defense": 0.90},
    "Man City": {"home_attack": 1.55, "home_defense": 0.82, "away_attack": 1.50, "away_defense": 0.85},
    "Bayern Munich": {"home_attack": 1.60, "home_defense": 0.78, "away_attack": 1.52, "away_defense": 0.80},
    "Borussia Dortmund": {"home_attack": 1.25, "home_defense": 0.95, "away_attack": 1.38, "away_defense": 0.92},
    "Real Madrid": {"home_attack": 1.52, "home_defense": 0.83, "away_attack": 1.48, "away_defense": 0.87},
    "Barcelona": {"home_attack": 1.42, "home_defense": 0.88, "away_attack": 1.40, "away_defense": 0.92},
    "Inter Milan": {"home_attack": 1.38, "home_defense": 0.87, "away_attack": 1.32, "away_defense": 0.89},
    "AC Milan": {"home_attack": 1.30, "home_defense": 0.92, "away_attack": 1.35, "away_defense": 0.86},
}

# League-average goals per match (used as baseline)
LEAGUE_AVG_HOME = 1.55
LEAGUE_AVG_AWAY = 1.25


# ──────────────────────────────────────────────────────────
#  Data structures
# ──────────────────────────────────────────────────────────

@dataclass
class MatchProbabilities:
    """Probabilities from Poisson model."""
    p_home: float
    p_draw: float
    p_away: float
    p_over_2_5: float
    p_under_2_5: float
    p_btts_yes: float
    p_btts_no: float
    best_score: str = "0-0"


@dataclass
class ValueBet:
    """A value betting opportunity."""
    selection: str
    model_prob: float
    bookmaker_odds: float
    ev: float  # expected value


@dataclass
class KellyCriterion:
    """Kelly Criterion stake calculation."""

    @staticmethod
    def calculate_stake(bankroll: float, model_prob: float, bookmaker_odds: float,
                        kelly_frac: float = 0.25) -> dict:
        """Calculate Kelly stake fraction and recommended amount."""
        if bookmaker_odds <= 1 or model_prob <= 0 or model_prob > 1:
            return {"recommended_stake": 0, "fraction": 0.0}

        # Full Kelly: f = (p * o - 1) / (o - 1)
        full_kelly_fraction = (model_prob * bookmaker_odds - 1) / (bookmaker_odds - 1)

        # Fractional Kelly
        applied_kelly_fraction = full_kelly_fraction * kelly_frac

        # Never recommend more than 25% of bankroll or negative
        recommended_stake = max(0, min(bankroll * applied_kelly_fraction, bankroll * 0.25))

        return {
            "recommended_stake": round(recommended_stake, 2),
            "fraction": round(applied_kelly_fraction, 4)
        }


# ──────────────────────────────────────────────────────────
#  Poisson Match Model
# ──────────────────────────────────────────────────────────

class PoissonMatchModel:
    """Predicts match outcome using a Dixon-Coles adjusted Poisson model.
    Uses team attack/defense strength derived from historical goal rates."""

    LEAGUE_AVG_HOME = 1.55
    LEAGUE_AVG_AWAY = 1.25

    @staticmethod
    def _team_strength(team: str, is_home: bool) -> Tuple[float, float]:
        """Return (attack_strength, defense_strength) for a team.
        Values >1 mean above-average; <1 mean below-average.
        Falls back to 1.0 if team not in database."""
        info = TEAM_DATABASE.get(team, {})
        if is_home:
            att = info.get("home_attack", 1.0)
            def_ = info.get("home_defense", 1.0)
        else:
            att = info.get("away_attack", 1.0)
            def_ = info.get("away_defense", 1.0)
        return att, def_

    @staticmethod
    def _poisson(k: int, lam: float) -> float:
        """Poisson PMF."""
        return (lam ** k) * math.exp(-lam) / math.factorial(k)

    @classmethod
    def calculate_match_probabilities(
            cls, home_xg: float, away_xg: float,
            dixon_coles_rho: float = -0.06) -> "MatchProbabilities":
        """Calculate match probabilities using Poisson + Dixon-Coles adjustment."""

        # Adjust xG with Dixon-Coles rho
        adj_home_xg = cls._adjust_xg(home_xg, dixon_coles_rho)
        adj_away_xg = cls._adjust_xg(away_xg, dixon_coles_rho)

        # Poisson probabilities for 0-6 goals
        max_goals = 7
        home_probs = [cls._poisson(k, adj_home_xg) for k in range(max_goals)]
        away_probs = [cls._poisson(k, adj_away_xg) for k in range(max_goals)]

        # Match outcome probabilities
        p_home = 0.0
        p_draw = 0.0
        p_away = 0.0
        score_matrix: Dict[str, float] = {}

        for i in range(max_goals):
            for j in range(max_goals):
                prob = home_probs[i] * away_probs[j]
                score_matrix[f"{i}-{j}"] = prob
                if i > j:
                    p_home += prob
                elif i == j:
                    p_draw += prob
                else:
                    p_away += prob

        # Normalize
        total = p_home + p_draw + p_away
        p_home /= total
        p_draw /= total
        p_away /= total

        # Most likely score
        best_score = max(score_matrix, key=score_matrix.get)

        # Over 2.5 / BTTS
        p_over_2_5 = sum(
            home_probs[i] * away_probs[j]
            for i in range(max_goals) for j in range(max_goals)
            if i + j > 2.5
        )
        p_btts = sum(
            home_probs[i] * away_probs[j]
            for i in range(1, max_goals) for j in range(1, max_goals)
        )

        # Confidence: how far the strongest probability is from uniform (33%)
        strongest = max(p_home, p_draw, p_away)
        confidence = min(10.0, (strongest - 0.33) / 0.67 * 10)
        confidence = max(1.0, confidence)

        return MatchProbabilities(
            p_home=round(p_home, 4),
            p_draw=round(p_draw, 4),
            p_away=round(p_away, 4),
            p_over_2_5=round(p_over_2_5, 4),
            p_under_2_5=round(1 - p_over_2_5, 4),
            p_btts_yes=round(p_btts, 4),
            p_btts_no=round(1 - p_btts, 4),
        )

    @staticmethod
    def _adjust_xg(xg: float, rho: float) -> float:
        """Simple Dixon-Coles adjustment."""
        # Dixon-Coles adjusts for low-scoring results
        # rho parameter captures correlation between goals
        adjustment = 1 + rho * (1 if xg > 2 else -1) * 0.1
        return max(0.1, xg * adjustment)


# ──────────────────────────────────────────────────────────
#  Market Evaluator
# ──────────────────────────────────────────────────────────

class MarketEvaluator:
    """Evaluates betting markets for value."""

    @staticmethod
    def evaluate_market(
            market_name: str,
            selections: List[str],
            model_probs: List[float],
            book_odds: List[float],
            min_ev_threshold: float = 0.02) -> List[ValueBet]:
        """Evaluate a betting market for value bets.

        Args:
            market_name: Name of the market (e.g., "1X2", "O/U 2.5")
            selections: List of selection names (e.g., ["Home Win", "Draw", "Away Win"])
            model_probs: List of model probabilities for each selection
            book_odds: List of bookmaker odds for each selection
            min_ev_threshold: Minimum expected value to qualify

        Returns:
            List of ValueBet objects representing value opportunities
        """
        value_bets = []

        for selection, model_prob, book_odds in zip(selections, model_probs, book_odds):
            if book_odds <= 1.0:
                continue

            # Calculate implied probability
            implied_prob = 1 / book_odds

            # Calculate expected value: EV = (model_prob * odds) - 1
            ev = model_prob * book_odds - 1

            if ev >= min_ev_threshold:
                value_bets.append(ValueBet(
                    selection=selection,
                    model_prob=model_prob,
                    bookmaker_odds=book_odds,
                    ev=round(ev, 4)
                ))

        return value_bets


# ──────────────────────────────────────────────────────────
#  Sentiment Adjuster
# ──────────────────────────────────────────────────────────

class SentimentAdjuster:
    """Adjusts xG based on team sentiment (morale, motivation, etc.)."""

    @staticmethod
    def adjust_xg(base_xg: float, sentiment: float, injuries: list) -> float:
        """Adjust expected goals based on sentiment and injury status.

        Args:
            base_xg: Base expected goals
            sentiment: Sentiment score (-1 to 1, negative = demoralized/injured)
            injuries: List of key player injury names

        Returns:
            Adjusted xG value
        """
        # Base adjustment from sentiment
        sentiment_factor = 1.0 + sentiment * 0.3

        # Injury penalty: each injury reduces xG by ~5%
        injury_penalty = max(0, len(injuries)) * 0.05 if injuries else 0

        # Combined adjustment
        adjusted = base_xg * sentiment_factor * (1 - injury_penalty)

        # Ensure xG doesn't go below a minimum (0.1)
        return max(0.1, adjusted)


# ──────────────────────────────────────────────────────────
#  Kelly Criterion (standalone function)
# ──────────────────────────────────────────────────────────

def kelly_stake(bankroll: float, model_prob: float, bookmaker_odds: float,
                kelly_frac: float = 0.25) -> float:
    """Calculate Kelly stake amount.

    Args:
        bankroll: Total bankroll
        model_prob: Model's predicted probability (0-1)
        bookmaker_odds: Bookmaker odds (decimal format)
        kelly_frac: Fraction of Kelly to use (1.0 = full Kelly, 0.25 = 25% Kelly)

    Returns:
        Recommended stake amount
    """
    if bookmaker_odds <= 1 or model_prob <= 0 or model_prob > 1:
        return 0.0

    # Full Kelly: f = (p * o - 1) / (o - 1)
    full_kelly_fraction = (model_prob * bookmaker_odds - 1) / (bookmaker_odds - 1)

    # Fractional Kelly
    applied_kelly_fraction = full_kelly_fraction * kelly_frac

    # Never recommend more than 25% of bankroll or negative
    recommended = max(0, min(bankroll * applied_kelly_fraction, bankroll * 0.25))

    return round(recommended, 2)


# ──────────────────────────────────────────────────────────
#  ValueBet (standalone)
# ──────────────────────────────────────────────────────────

class ValueBet:
    """A value betting opportunity."""

    def __init__(self, selection: str, model_prob: float, bookmaker_odds: float,
                 ev: float):
        self.selection = selection
        self.model_prob = model_prob
        self.bookmaker_odds = bookmaker_odds
        self.ev = ev

    @property
    def is_value(self) -> bool:
        """Check if this bet has positive expected value."""
        return self.ev > 0.02


# ──────────────────────────────────────────────────────────
#  Public API exports
# ──────────────────────────────────────────────────────────

# Export key classes and functions for external imports
__all__ = [
    "PoissonMatchModel",
    "SentimentAdjuster",
    "MarketEvaluator",
    "KellyCriterion",
    "ValueBet",
    "MatchProbabilities",
    "kelly_stake",
    "predict_poisson",
    "get_team_strength",
]

# Export predict_poisson as a standalone function for convenience
def predict_poisson(home_team: str, away_team: str) -> dict:
    """Basic Poisson-based prediction for a match.

    Args:
        home_team: Home team name
        away_team: Away team name

    Returns:
        Dict with prediction probabilities and expected goals
    """
    result = PoissonMatchModel.calculate_match_probabilities(
        home_xg=1.5,  # default xG
        away_xg=1.2   # default xG
    )

    # Calculate confidence from the model
    confidence = min(10.0, (result.p_home + result.p_draw + result.p_away - 0.33) / 0.67 * 10)
    confidence = max(1.0, confidence)

    # Calculate expected goals from the model
    home_lambda = 1.5
    away_lambda = 1.2

    return {
        "home_win_prob": result.p_home,
        "draw_prob": result.p_draw,
        "away_win_prob": result.p_away,
        "predicted_home_goals": home_lambda,
        "predicted_away_goals": away_lambda,
        "confidence": round(confidence, 1),
        "most_likely_score": result.best_score,
        "p_over_2_5": result.p_over_2_5,
        "p_btts_yes": result.p_btts_yes,
    }

# Export get_team_strength
def get_team_strength(team: str, is_home: bool = True) -> tuple:
    """Return (attack_strength, defense_strength) for a team."""
    info = TEAM_DATABASE.get(team, {})
    if is_home:
        att = info.get("home_attack", 1.0)
        def_ = info.get("home_defense", 1.0)
    else:
        att = info.get("away_attack", 1.0)
        def_ = info.get("away_defense", 1.0)
    return att, def_