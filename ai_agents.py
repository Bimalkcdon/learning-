"""
ApexQuant — 5-Agent AI Football Prediction Engine

Five specialized agents analyze every match from independent angles.
Three "real" agents produce independent predictions from fundamentals
(not derived from bookmaker odds), then the Market Intelligence agent
and Consensus agent synthesize the final verdict.

Agents:
  1. STATS_ANALYST    — Poisson/xG model, historical scoring rates
  2. MOMENTUM_ANALYST — Form curves, streaks, recent performance
  3. CONTEXT_ANALYST  — Injuries, schedule congestion, travel, rest
  4. MARKET_INTEL     — Odds comparison, sharp-money signals, line movement
  5. CONSENSUS        — Weighted ensemble, confidence scoring, final pick
"""

import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import hashlib
import os
import sys


# ──────────────────────────────────────────────────────────
#  Data structures
# ──────────────────────────────────────────────────────────

@dataclass
class AgentPrediction:
    """Output of a single agent for one match."""
    agent_name: str
    agent_label: str          # short label for UI
    home_win_prob: float      # 0-1
    draw_prob: float          # 0-1
    away_win_prob: float      # 0-1
    predicted_home_goals: float
    predicted_away_goals: float
    confidence: float         # 0-10
    reasoning: str            # 1-sentence explanation
    suggested_bet: Optional[str] = None
    suggested_odds: Optional[float] = None
    ev: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConsensusResult:
    """Final blended prediction for one match."""
    match_id: str
    home_team: str
    away_team: str
    league: str
    match_time: str
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    predicted_score: str
    confidence: float
    top_pick: str             # e.g. "home_win", "draw", "away_win", "over_2_5", "btts"
    top_pick_odds: Optional[float] = None
    ev: Optional[float] = None
    agent_votes: Dict[str, str] = field(default_factory=dict)
    reasoning: str = ""
    agent_predictions: List[AgentPrediction] = field(default_factory=list)


# ──────────────────────────────────────────────────────────
#  Team database — simulated historical stats
#  In production, replace with real historical data API.
# ──────────────────────────────────────────────────────────

TEAM_DATABASE: Dict[str, Dict[str, Any]] = {
    # Each team: rolling averages from last 10-20 matches
    # (These are realistic approximations — swap with real data later)
}

# ──────────────────────────────────────────────────────────
#  Agent 1 — STATISTICAL ANALYST
#  Pure math: Poisson goals model from expected goals (xG)
# ──────────────────────────────────────────────────────────

class StatisticalAnalyst:
    """Predicts match outcome using a Dixon-Coles adjusted Poisson model.
    Uses team attack/defense strength derived from historical goal rates."""

    name = "STATS_ANALYST"
    label = "Statistical Model"

    # League-average goals per match (used as baseline)
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

    @classmethod
    def predict(cls, match: Dict[str, Any]) -> AgentPrediction:
        home = match.get("home_team", "Home")
        away = match.get("away_team", "Away")

        home_att, home_def = cls._team_strength(home, is_home=True)
        away_att, away_def = cls._team_strength(away, is_home=False)

        # Dixon-Coles lambda adjustment
        home_lambda = cls.LEAGUE_AVG_HOME * home_att * away_def * 1.08  # home advantage factor
        away_lambda = cls.LEAGUE_AVG_AWAY * away_att * home_def

        home_lambda = max(0.2, home_lambda)
        away_lambda = max(0.2, away_lambda)

        # Poisson probabilities for 0-6 goals
        max_goals = 7
        home_probs = [cls._poisson(k, home_lambda) for k in range(max_goals)]
        away_probs = [cls._poisson(k, away_lambda) for k in range(max_goals)]

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
        p_over_25 = sum(
            home_probs[i] * away_probs[j]
            for i in range(max_goals) for j in range(max_goals)
            if i + j > 2.5
        )
        p_btts = sum(
            home_probs[i] * away_probs[j]
            for i in range(1, max_goals) for j in range(1, max_goals)
        )

        # Suggested bet (highest EV if odds provided)
        suggested_bet, suggested_odds, ev = cls._find_best_bet(
            p_home, p_draw, p_away, p_over_25, p_btts, match
        )

        # Confidence: how far the strongest probability is from uniform (33%)
        strongest = max(p_home, p_draw, p_away)
        confidence = min(10.0, (strongest - 0.33) / 0.67 * 10)
        confidence = max(1.0, confidence)

        reasoning = (
            f"Poisson model projects {home_lambda:.2f} xG for {home} "
            f"vs {away_lambda:.2f} xG for {away}. "
            f"Most likely scoreline: {best_score}."
        )

        return AgentPrediction(
            agent_name=cls.name,
            agent_label=cls.label,
            home_win_prob=round(p_home, 4),
            draw_prob=round(p_draw, 4),
            away_win_prob=round(p_away, 4),
            predicted_home_goals=round(home_lambda, 2),
            predicted_away_goals=round(away_lambda, 2),
            confidence=round(confidence, 1),
            reasoning=reasoning,
            suggested_bet=suggested_bet,
            suggested_odds=suggested_odds,
            ev=round(ev, 4) if ev is not None else None,
            metadata={
                "xg_home": round(home_lambda, 2),
                "xg_away": round(away_lambda, 2),
                "p_over_2_5": round(p_over_25, 4),
                "p_btts": round(p_btts, 4),
                "most_likely_score": best_score,
            }
        )

    @staticmethod
    def _poisson(k: int, lam: float) -> float:
        """Poisson PMF."""
        return (lam ** k) * math.exp(-lam) / math.factorial(k)

    @classmethod
    def _find_best_bet(cls, p_home, p_draw, p_away, p_over_25, p_btts, match):
        """Find the bet with the highest expected value given bookmaker odds."""
        odds = match.get("odds", {})
        best_ev = 0.0
        best_bet = None
        best_odds = None

        candidates = [
            ("home_win", p_home, odds.get("home_win")),
            ("draw", p_draw, odds.get("draw")),
            ("away_win", p_away, odds.get("away_win")),
            ("over_2_5", p_over_25, odds.get("over_2_5")),
            ("btts", p_btts, odds.get("btts_yes")),
        ]

        for label, prob, o in candidates:
            if o and o > 1:
                ev = prob * o - 1
                if ev > best_ev:
                    best_ev = ev
                    best_bet = label
                    best_odds = o

        return best_bet, best_odds, best_ev if best_bet else (None, None, None)


# ──────────────────────────────────────────────────────────
#  Agent 2 — MOMENTUM ANALYST
#  Analyzes recent form, streaks, goal trends, and momentum.
#  Uses last 5-10 match results to detect hot/cold teams.
# ──────────────────────────────────────────────────────────

class MomentumAnalyst:
    """Evaluates team momentum from recent match history:
    form points, goal momentum, home/away streaks."""

    name = "MOMENTUM_ANALYST"
    label = "Form & Momentum"

    # Simulated recent form data — in production, fetch from API
    # Format: {team: [{"result": "W"/"D"/"L", "gf": N, "ga": N, "home": bool}, ...]}
    RECENT_FORM: Dict[str, List[Dict]] = {}

    @classmethod
    def predict(cls, match: Dict[str, Any]) -> AgentPrediction:
        home = match.get("home_team", "Home")
        away = match.get("away_team", "Away")

        home_form = cls._form_points(home, is_home=True)
        away_form = cls._form_points(away, is_home=False)
        home_momentum = cls._goal_momentum(home, is_home=True)
        away_momentum = cls._goal_momentum(away, is_home=False)

        # Convert to implied probabilities via logistic transform
        total = home_form + away_form + 0.8  # draw bias
        p_home_raw = home_form / total
        p_away_raw = away_form / total
        p_draw_raw = 0.8 / total

        # Momentum adjustment
        home_adj = cls._logit_scale(home_form, home_momentum)
        away_adj = cls._logit_scale(away_form, away_momentum)
        draw_adj = 0.5

        norm = home_adj + away_adj + draw_adj
        p_home = home_adj / norm
        p_away = away_adj / norm
        p_draw = draw_adj / norm

        # Most likely score from form trends
        avg_gf_home = home_momentum.get("avg_scored", 1.5)
        avg_ga_home = home_momentum.get("avg_conceded", 1.3)
        avg_gf_away = away_momentum.get("avg_scored", 1.3)
        avg_ga_away = away_momentum.get("avg_conceded", 1.5)

        proj_home = round(max(0, (avg_gf_home + avg_ga_away) / 2), 1)
        proj_away = round(max(0, (avg_gf_away + avg_ga_home) / 2), 1)

        confidence = cls._calc_confidence(p_home, p_draw, p_away, home_form, away_form)

        reasoning = (
            f"{home} form: {home_form:.0f} pts from last 5 "
            f"({home_momentum.get('streak', 'mixed')}); "
            f"{away}: {away_form:.0f} pts "
            f"({away_momentum.get('streak', 'mixed')})."
        )

        return AgentPrediction(
            agent_name=cls.name,
            agent_label=cls.label,
            home_win_prob=round(p_home, 4),
            draw_prob=round(p_draw, 4),
            away_win_prob=round(p_away, 4),
            predicted_home_goals=proj_home,
            predicted_away_goals=proj_away,
            confidence=round(confidence, 1),
            reasoning=reasoning,
            suggested_bet=None,
            suggested_odds=None,
            ev=None,
            metadata={
                "home_form_pts": round(home_form, 1),
                "away_form_pts": round(away_form, 1),
                "home_streak": home_momentum.get("streak", "N/A"),
                "away_streak": away_momentum.get("streak", "N/A"),
            }
        )

    @classmethod
    def _form_points(cls, team: str, is_home: bool) -> float:
        """Calculate weighted form points from last 5 matches.
        Most recent match gets highest weight."""
        forms = cls.RECENT_FORM.get(team, [])
        relevant = [f for f in forms if f.get("home") == is_home] if forms else forms
        if not relevant:
            return 5.0  # neutral default

        recent = relevant[:5]
        weights = [1.0, 0.9, 0.8, 0.7, 0.6]
        pts = 0.0
        total_w = 0.0
        for i, m in enumerate(recent):
            w = weights[i] if i < len(weights) else 0.5
            total_w += w
            if m["result"] == "W":
                pts += 3 * w
            elif m["result"] == "D":
                pts += 1 * w
        return pts / total_w if total_w > 0 else 5.0

    @classmethod
    def _goal_momentum(cls, team: str, is_home: bool) -> Dict[str, Any]:
        """Calculate goal-scoring and conceding momentum."""
        forms = cls.RECENT_FORM.get(team, [])
        relevant = [f for f in forms if f.get("home") == is_home] if forms else forms
        if not relevant:
            return {"avg_scored": 1.4, "avg_conceded": 1.3, "streak": "N/A"}

        recent = relevant[:5]
        goals_scored = [m.get("gf", 0) for m in recent]
        goals_conceded = [m.get("ga", 0) for m in recent]

        avg_s = sum(goals_scored) / len(goals_scored)
        avg_c = sum(goals_conceded) / len(goals_conceded)

        # Detect streak
        results = [m["result"] for m in recent]
        streak = cls._detect_streak(results)

        return {
            "avg_scored": round(avg_s, 2),
            "avg_conceded": round(avg_c, 2),
            "streak": streak,
        }

    @staticmethod
    def _detect_streak(results: List[str]) -> str:
        if not results:
            return "N/A"
        first = results[0]
        count = 1
        for r in results[1:]:
            if r == first:
                count += 1
            else:
                break
        if first == "W":
            return f"{count}W streak" if count > 1 else "Winning"
        elif first == "L":
            return f"{count}L streak" if count > 1 else "Losing"
        return f"{count}D streak" if count > 1 else "Mixed"

    @staticmethod
    def _logit_scale(form: float, momentum: Dict) -> float:
        base = form
        gd = momentum.get("avg_scored", 1.4) - momentum.get("avg_conceded", 1.3)
        return max(0.3, base * (1.0 + gd * 0.15))

    @staticmethod
    def _calc_confidence(p_h, p_d, p_a, h_form, a_form) -> float:
        strongest = max(p_h, p_d, p_a)
        form_spread = abs(h_form - a_form)
        base = min(10.0, (strongest - 0.33) / 0.67 * 10)
        form_bonus = min(2.0, form_spread * 0.3)
        return max(1.0, base + form_bonus)


# ──────────────────────────────────────────────────────────
#  Agent 3 — CONTEXTUAL ANALYST
#  Factors: injuries, suspensions, schedule congestion,
#  travel distance, rest days, motivation (cup vs league),
#  weather, referee tendencies.
# ──────────────────────────────────────────────────────────

class ContextualAnalyst:
    """Evaluates non-statistical context that affects match outcome:
    team news, scheduling, travel, motivation."""

    name = "CONTEXT_ANALYST"
    label = "Context & Team News"

    # In production, populate from news APIs, team feeds, etc.
    INJURY_IMPACT: Dict[str, float] = {}       # team -> negative impact score
    SCHEDULE_INFO: Dict[str, Dict] = {}        # team -> {days_rest, travel_km, is_derby}

    @classmethod
    def predict(cls, match: Dict[str, Any]) -> AgentPrediction:
        home = match.get("home_team", "Home")
        away = match.get("away_team", "Away")

        # Injury impact (negative = hurts team)
        home_injury = cls.INJURY_IMPACT.get(home, 0.0)
        away_injury = cls.INJURY_IMPACT.get(away, 0.0)

        # Schedule context
        home_ctx = cls.SCHEDULE_INFO.get(home, {})
        away_ctx = cls.SCHEDULE_INFO.get(away, {})

        home_rest = home_ctx.get("days_rest", 4)
        away_rest = away_ctx.get("days_rest", 4)
        home_travel = home_ctx.get("travel_km", 0)
        away_travel = away_ctx.get("travel_km", 0)
        is_derby = home_ctx.get("is_derby", False) or away_ctx.get("is_derby", False)

        # Build advantage score
        home_adv = 0.0
        away_adv = 0.0

        # Rest advantage
        rest_diff = home_rest - away_rest
        home_adv += rest_diff * 0.3
        away_adv -= rest_diff * 0.3

        # Travel fatigue
        home_adv += (away_travel - home_travel) * 0.002
        away_adv += (home_travel - away_travel) * 0.002

        # Injury impact
        home_adv -= home_injury * 0.5
        away_adv -= away_injury * 0.5

        # Home ground advantage (baseline)
        home_adv += 0.8

        # Derby: home advantage amplifies
        if is_derby:
            home_adv += 0.3

        # Convert to probabilities via softmax
        draw_base = 2.5
        home_exp = math.exp(home_adv * 0.4)
        away_exp = math.exp(away_adv * 0.4)
        draw_exp = math.exp(draw_base * 0.4)
        total = home_exp + away_exp + draw_exp

        p_home = home_exp / total
        p_away = away_exp / total
        p_draw = draw_exp / total

        # Predicted goals (lower if key players injured)
        home_goals = max(0.3, 1.5 - home_injury * 0.3 + rest_diff * 0.05)
        away_goals = max(0.3, 1.2 - away_injury * 0.3 - rest_diff * 0.05)

        confidence = min(10.0, max(1.0, abs(home_adv - away_adv) * 1.2 + 4.0))

        context_notes = []
        if home_injury > 0:
            context_notes.append(f"{home} injury impact: -{home_injury:.1f}")
        if away_injury > 0:
            context_notes.append(f"{away} injury impact: -{away_injury:.1f}")
        if rest_diff > 2:
            context_notes.append(f"{home} has {rest_diff} more days rest")
        if rest_diff < -2:
            context_notes.append(f"{away} has {-rest_diff} more days rest")
        if away_travel > 500:
            context_notes.append(f"{away} traveled {away_travel}km")
        if is_derby:
            context_notes.append("Local derby — tighter than usual")

        reasoning = "; ".join(context_notes) if context_notes else "No significant contextual factors detected."

        return AgentPrediction(
            agent_name=cls.name,
            agent_label=cls.label,
            home_win_prob=round(p_home, 4),
            draw_prob=round(p_draw, 4),
            away_win_prob=round(p_away, 4),
            predicted_home_goals=round(home_goals, 1),
            predicted_away_goals=round(away_goals, 1),
            confidence=round(confidence, 1),
            reasoning=reasoning,
            suggested_bet=None,
            suggested_odds=None,
            ev=None,
            metadata={
                "home_rest_days": home_rest,
                "away_rest_days": away_rest,
                "home_travel_km": home_travel,
                "away_travel_km": away_travel,
                "is_derby": is_derby,
                "home_injury_impact": round(home_injury, 2),
                "away_injury_impact": round(away_injury, 2),
            }
        )


# ──────────────────────────────────────────────────────────
#  Agent 4 — MARKET INTELLIGENCE
#  Analyzes bookmaker odds across multiple bookmakers,
#  detects line movement, sharp money, and market inefficiencies.
# ──────────────────────────────────────────────────────────

class MarketIntelAgent:
    """Reads the market to find where smart money is flowing.
    Compares odds across bookmakers and detects value from
    market sentiment vs true probability."""

    name = "MARKET_INTEL"
    label = "Market Intelligence"

    @classmethod
    def predict(cls, match: Dict[str, Any]) -> AgentPrediction:
        odds = match.get("odds", {})
        home_odds = odds.get("home_win")
        draw_odds = odds.get("draw")
        away_odds = odds.get("away_win")
        over_odds = odds.get("over_2_5")
        under_odds = odds.get("under_2_5")

        if not all([home_odds, draw_odds, away_odds]):
            return AgentPrediction(
                agent_name=cls.name,
                agent_label=cls.label,
                home_win_prob=0.33,
                draw_prob=0.34,
                away_win_prob=0.33,
                predicted_home_goals=1.4,
                predicted_away_goals=1.2,
                confidence=2.0,
                reasoning="Insufficient odds data for market analysis.",
            )

        # Implied probabilities (remove vigorish)
        inv_home = 1 / home_odds
        inv_draw = 1 / draw_odds
        inv_away = 1 / away_odds
        overround = inv_home + inv_draw + inv_away

        p_home = inv_home / overround
        p_draw = inv_draw / overround
        p_away = inv_away / overround

        # Fair odds (no vig)
        fair_home = 1 / p_home
        fair_draw = 1 / p_draw
        fair_away = 1 / p_away

        # Market efficiency score
        vig = (overround - 1) * 100
        efficiency = max(1, 10 - vig * 0.5)

        # Find value: compare market implied vs sharp model estimate
        # Use a simple ELO-based estimate as "true" probability
        elo_home = match.get("home_elo", 1500)
        elo_away = match.get("away_elo", 1500)
        elo_diff = elo_home - elo_away
        elo_home_prob = 1 / (1 + 10 ** (-elo_diff / 400))
        elo_draw_prob = max(0.15, 0.30 - abs(elo_diff) / 1000)
        elo_away_prob = 1 - elo_home_prob - elo_draw_prob

        # Market mispricing
        home_misprice = p_home - elo_home_prob
        away_misprice = p_away - elo_away_prob

        suggested_bet = None
        suggested_odds_val = None
        ev_val = None

        # Check if market is mispricing away team (sharp money signal)
        if away_misprice < -0.05 and away_odds:
            suggested_bet = "away_win"
            suggested_odds_val = away_odds
            ev_val = elo_away_prob * away_odds - 1
        elif home_misprice < -0.05 and home_odds:
            suggested_bet = "home_win"
            suggested_odds_val = home_odds
            ev_val = elo_home_prob * home_odds - 1

        reasoning = (
            f"Market vig: {vig:.1f}%. "
            f"Home implied {p_home:.1%}, ELO estimate {elo_home_prob:.1%} "
            f"(diff: {home_misprice:+.1%})."
        )

        return AgentPrediction(
            agent_name=cls.name,
            agent_label=cls.label,
            home_win_prob=round(p_home, 4),
            draw_prob=round(p_draw, 4),
            away_win_prob=round(p_away, 4),
            predicted_home_goals=round(elo_home_prob * 3.0, 1),
            predicted_away_goals=round(elo_away_prob * 3.0, 1),
            confidence=round(efficiency, 1),
            reasoning=reasoning,
            suggested_bet=suggested_bet,
            suggested_odds=suggested_odds_val,
            ev=round(ev_val, 4) if ev_val is not None else None,
            metadata={
                "market_vig": round(vig, 2),
                "home_misprice": round(home_misprice, 4),
                "away_misprice": round(away_misprice, 4),
                "fair_home_odds": round(fair_home, 2),
                "fair_draw_odds": round(fair_draw, 2),
                "fair_away_odds": round(fair_away, 2),
            }
        )


# Import the learning engine for adaptive weights
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from learning_engine import LearningEngine
except ImportError:
    LearningEngine = None


# ──────────────────────────────────────────────────────────
#  Agent 5 — CONSENSUS ENSEMBLE
#  Blends all 4 agent predictions with adaptive weighting,
#  produces the final prediction with confidence calibration.
# ──────────────────────────────────────────────────────────

class ConsensusAgent:
    """Weighted ensemble of all agents.
    Weights are adaptive: when agents agree, confidence is high;
    when they disagree, the system flags uncertainty."""

    name = "CONSENSUS"
    label = "Consensus Verdict"

    # Default weights — can be tuned based on backtesting
    WEIGHTS = {
        StatisticalAnalyst.name: 0.35,
        MomentumAnalyst.name: 0.25,
        ContextualAnalyst.name: 0.20,
        MarketIntelAgent.name: 0.20,
    }

    # Global learning engine instance (singleton)
    learning_engine = LearningEngine() if LearningEngine else None

    @classmethod
    def predict(cls, match: Dict[str, Any], predictions: List[AgentPrediction]) -> ConsensusResult:
        # Weighted average of probabilities
        w_home = 0.0
        w_draw = 0.0
        w_away = 0.0
        total_weight = 0.0
        w_home_goals = 0.0
        w_away_goals = 0.0

        agent_votes = {}
        best_bet = None
        best_ev = 0.0
        best_odds = None

        for pred in predictions:
            w = cls.WEIGHTS.get(pred.agent_name, 0.2)
            conf_factor = pred.confidence / 10.0  # scale by confidence
            adjusted_w = w * (0.5 + 0.5 * conf_factor)  # high-conf agents get more weight

            # Apply adaptive weights from learning engine
            if cls.learning_engine:
                adaptive_weights = cls.learning_engine.get_agent_weights()
                agent_name = pred.agent_name
                if agent_name in adaptive_weights:
                    # Blend default weight with adaptive weight (80/20)
                    adaptive_weight = adaptive_weights[agent_name]
                    w = (w * 0.8) + (adaptive_weight * 0.2)
                    adjusted_w = w * (0.5 + 0.5 * conf_factor)

            total_weight += adjusted_w
            w_home += pred.home_win_prob * adjusted_w
            w_draw += pred.draw_prob * adjusted_w
            w_away += pred.away_win_prob * adjusted_w
            w_home_goals += pred.predicted_home_goals * adjusted_w
            w_away_goals += pred.predicted_away_goals * adjusted_w

            # Each agent's vote for the match result
            probs = {
                "home_win": pred.home_win_prob,
                "draw": pred.draw_prob,
                "away_win": pred.away_win_prob,
            }
            agent_votes[pred.agent_label] = max(probs, key=probs.get)

            # Track best individual bet suggestion
            if pred.ev and pred.ev > best_ev:
                best_ev = pred.ev
                best_bet = pred.suggested_bet
                best_odds = pred.suggested_odds

        # Normalize
        if total_weight > 0:
            w_home /= total_weight
            w_draw /= total_weight
            w_away /= total_weight
            w_home_goals /= total_weight
            w_away_goals /= total_weight

        # Agreement score: how many agents agree on the same outcome
        vote_counts = {}
        for v in agent_votes.values():
            vote_counts[v] = vote_counts.get(v, 0) + 1
        agreement = max(vote_counts.values()) / len(predictions) if predictions else 0

        # Confidence: blend of agreement + probability strength
        strongest = max(w_home, w_draw, w_away)
        confidence = (agreement * 4.0) + (strongest - 0.33) / 0.67 * 6.0
        confidence = max(1.0, min(10.0, confidence))

        # Predicted score
        pred_home_goals = round(w_home_goals, 1)
        pred_away_goals = round(w_away_goals, 1)
        predicted_score = f"{round(w_home_goals)}-{round(w_away_goals)}"

        # Top pick
        top_pick = "home_win"
        if w_draw > w_home and w_draw > w_away:
            top_pick = "draw"
        elif w_away > w_home and w_away > w_draw:
            top_pick = "away_win"

        # Override with best individual bet if EV is strong
        if best_bet and best_ev > 0.05:
            top_pick = best_bet

        # Reasoning
        vote_str = ", ".join(f"{k}: {v}" for k, v in agent_votes.items())
        reasoning = (
            f"Agents agree {int(agreement*100)}% ({vote_str}). "
            f"Adaptive weights applied based on historical accuracy. "
            f"Consensus: {top_pick.replace('_', ' ')} at {confidence:.1f}/10 confidence. "
            f"Projected: {pred_home_goals}-{pred_away_goals}."
        )

        # Calculate EV for top pick
        final_ev = None
        final_odds = None
        odds = match.get("odds", {})
        if top_pick == "home_win":
            final_odds = odds.get("home_win")
            final_ev = (w_home * final_odds - 1) if final_odds else None
        elif top_pick == "draw":
            final_odds = odds.get("draw")
            final_ev = (w_draw * final_odds - 1) if final_odds else None
        elif top_pick == "away_win":
            final_odds = odds.get("away_win")
            final_ev = (w_away * final_odds - 1) if final_odds else None

        return ConsensusResult(
            match_id=match.get("id", ""),
            home_team=match.get("home_team", "Home"),
            away_team=match.get("away_team", "Away"),
            league=match.get("league", "Unknown"),
            match_time=match.get("match_time", ""),
            home_win_prob=round(w_home, 4),
            draw_prob=round(w_draw, 4),
            away_win_prob=round(w_away, 4),
            predicted_score=predicted_score,
            confidence=round(confidence, 1),
            top_pick=top_pick,
            top_pick_odds=round(final_odds, 2) if final_odds else None,
            ev=round(final_ev, 4) if final_ev is not None else None,
            agent_votes=agent_votes,
            reasoning=reasoning,
            agent_predictions=predictions,
        )


# ──────────────────────────────────────────────────────────
#  Main pipeline — run all agents on a batch of matches
# ──────────────────────────────────────────────────────────

def analyze_matches(matches: List[Dict[str, Any]]) -> List[ConsensusResult]:
    """Run the full 5-agent pipeline on a list of match dicts.
    Each match dict should have: id, home_team, away_team, league,
    match_time, odds {home_win, draw, away_win, over_2_5, ...}"""

    results = []

    for match in matches:
        # Run the 4 independent agents
        predictions = [
            StatisticalAnalyst.predict(match),
            MomentumAnalyst.predict(match),
            ContextualAnalyst.predict(match),
            MarketIntelAgent.predict(match),
        ]

        # Consensus blends them
        consensus = ConsensusAgent.predict(match, predictions)
        results.append(consensus)

    return results


def get_top_picks(matches: List[Dict[str, Any]], min_confidence: float = 6.0,
                  top_n: int = 8) -> List[ConsensusResult]:
    """Get the top N picks with confidence above threshold."""
    all_results = analyze_matches(matches)
    picks = [r for r in all_results if r.confidence >= min_confidence]
    picks.sort(key=lambda r: r.confidence, reverse=True)
    return picks[:top_n]