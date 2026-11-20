import os
import json
from datetime import datetime
from collections import defaultdict

class LearningEngine:
    DEFAULT_STORE = "predictions.json"
    AGENT_NAMES = ["STATS_ANALYST", "MOMENTUM_ANALYST", "CONTEXT_ANALYST", "MARKET_INTEL"]
    BASE_WEIGHTS = {
        "STATS_ANALYST": 0.35,
        "MOMENTUM_ANALYST": 0.25,
        "CONTEXT_ANALYST": 0.20,
        "MARKET_INTEL": 0.20,
    }

    def __init__(self, store_path: str = None):
        self.store_path = store_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), self.DEFAULT_STORE)
        self.data = self._load()
        self.team_database = self.data.get("team_database", {})

    def _load(self) -> dict:
        if os.path.exists(self.store_path):
            try:
                with open(self.store_path, "r") as f:
                    data = json.load(f)
                return {
                    "predictions": data.get("predictions", []),
                    "results": data.get("results", {}),
                    "agent_history": defaultdict(list, data.get("agent_history", {})),
                    "team_database": data.get("team_database", {}),
                    "last_updated": data.get("last_updated"),
                }
            except json.JSONDecodeError:
                pass
        return {
            "predictions": [],
            "results": {},
            "agent_history": defaultdict(list),
            "team_database": {},
            "last_updated": None,
        }

    def _save(self) -> None:
        serializable = {
            "predictions": self.data["predictions"],
            "results": self.data["results"],
            "agent_history": dict(self.data["agent_history"]),
            "team_database": self.data.get("team_database", {}),
            "last_updated": datetime.now().isoformat(),
        }
        with open(self.store_path, "w") as f:
            json.dump(serializable, f, indent=2)

    def log_prediction(self, prediction: dict) -> None:
        # Existing logging logic with team_database check
        for existing in self.data["predictions"]:
            if existing.get("match_id") == prediction.get("match_id"):
                return
        self.data["predictions"].append(prediction)
        self.data["predictions"] = self.data["predictions"][-1000:]
        self._save()

    def record_result(self, match_id: str, home_score: int, away_score: int) -> bool:
        # Existing result recording
        self.data["results"][match_id] = {
            "home_score": home_score,
            "away_score": away_score,
            "result": self._outcome(home_score, away_score),
            "recorded_at": datetime.now().isoformat(),
        }
        prediction = self._find_prediction(match_id)
        if prediction:
            self._score_prediction(prediction, home_score, away_score)
            self._update_team_ratings(prediction, home_score, away_score)
            return True
        self._save()
        return False

    def _update_team_ratings(self, prediction: dict, home_score: int, away_score: int) -> None:
        # Update team strengths based on prediction errors
        home_team = prediction["home_team"]
        away_team = prediction["away_team"]
        agents = prediction.get("agents", [])

        # Initialize teams in database if missing
        for team in [home_team, away_team]:
            if team not in self.team_database:
                self.team_database[team] = {
                    "home_attack": 1.0, "home_defense": 1.0,
                    "away_attack": 1.0, "away_defense": 1.0,
                    "adjustment_factor": 0.1  # Controls learning rate
                }

        # Calculate actual vs predicted goal differentials
        actual_diff = home_score - away_score
        for agent in agents:
            if agent["name"] != "STATS_ANALYST":  # Only use statistical model for updates
                continue
            pred_diff = agent["predicted_home_goals"] - agent["predicted_away_goals"]
            error = actual_diff - pred_diff

            # Adjust home team ratings
            self._adjust_team(home_team, True, error, actual_diff > 0)
            # Adjust away team ratings
            self._adjust_team(away_team, False, -error, actual_diff < 0)

        self._save()  # Persist updated ratings

    def _adjust_team(self, team: str, is_home: bool, error: float, won: bool) -> None:
        # Adjust attack/defense based on error and outcome
        # Learning rate controlled by adjustment_factor
        params = self.team_database[team]
        learn_rate = params["adjustment_factor"]

        if is_home:
            # Home team: attack if won, defense if lost
            params["home_attack"] *= 1 + learn_rate * (won ? 0.1 : -0.1)
            params["home_defense"] *= 1 + learn_rate * (won ? 0.1 : -0.1)
        else:
            # Away team: attack if lost (underperformed), defense if won
            params["away_attack"] *= 1 + learn_rate * (won ? -0.1 : 0.1)
            params["away_defense"] *= 1 + learn_rate * (won ? -0.1 : 0.1)

        # Gradually decay learning rate
        params["adjustment_factor"] *= 0.995

    # Existing methods (_find_prediction, _score_prediction, etc.) remain unchanged

    def get_agent_weights(self, lookback: int = 50) -> dict:
        # ... (existing implementation)

    def get_stats(self) -> dict:
        # Include team database in stats for monitoring
        stats = {
            # ... existing stats
            "team_database": self.team_database
        }
        return stats

# Updated agent prediction method (example for STATS_ANALYST)
def predict_match(match: dict, team_database: dict) -> dict:
    home_team = match["home_team"]
    away_team = match["away_team"]

    # Get team strengths from updated database
    home_att = team_database.get(home_team, {}).get("home_attack", 1.0)
    home_def = team_database.get(home_team, {}).get("home_defense", 1.0)
    away_att = team_database.get(away_team, {}).get("away_attack", 1.0)
    away_def = team_database.get(away_team, {}).get("away_defense", 1.0)

    # Calculate expected goals using updated strengths
    # ... rest of prediction logic

# Usage in server.py
engine = LearningEngine()
team_database = engine.data.get("team_database", {})

# When making predictions
for match in matches:
    prediction = predict_match(match, team_database)
    engine.log_prediction(prediction)