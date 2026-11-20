"""
ApexQuant — AI Council System (Stub Module)
Provides AI Council verification, ResourceDataManager, and MatchResources.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class MatchResources:
    """Resources available for AI Council verification."""
    home_form: float = 5.0
    away_form: float = 5.0
    home_rest_days: int = 6
    away_rest_days: int = 6
    home_injury_count: int = 0
    away_injury_count: int = 0
    home_travel_km: int = 0
    away_travel_km: int = 0
    is_home_derby: bool = False
    is_away_derby: bool = False
    stadium_capacity: int = 50000


class ResourceDataManager:
    """Manages resource data for AI Council verification."""

    @staticmethod
    def get_mock_resources(fixture_id: str) -> MatchResources:
        """Get mock resources for a fixture. In production, these would come from databases."""
        return MatchResources(
            home_form=round(5.0 + __import__('random').uniform(-1.0, 1.0), 1),
            away_form=round(5.0 + __import__('random').uniform(-1.0, 1.0), 1),
            home_rest_days=__import__('random').randint(3, 7),
            away_rest_days=__import__('random').randint(3, 7),
            home_injury_count=__import__('random').randint(0, 3),
            away_injury_count=__import__('random').randint(0, 3),
            home_travel_km=__import__('random').randint(0, 500),
            away_travel_km=__import__('random').randint(0, 500),
            is_home_derby=__import__('random').random() > 0.7,
            is_away_derby=__import__('random').random() > 0.7,
            stadium_capacity=__import__('random').randint(15000, 80000),
        )


class AICouncil:
    """AI Council that verifies predictions and provides consensus."""

    @staticmethod
    def verify_prediction(pred_data: Dict[str, Any], resources: MatchResources) -> Dict[str, Any]:
        """Verify a prediction using council resources and return verification results."""
        ev = pred_data.get("ev", 0.0)
        # Use 'fraction' key from Kelly output, default to 0.5 if missing
        kelly_frac = pred_data.get("fraction", 0.5)
        confidence = kelly_frac * 10.0

        # Factor in resources
        form_adjustment = (resources.home_form - resources.away_form) * 0.02
        confidence = max(1.0, min(10.0, confidence + form_adjustment))

        # Determine consensus
        if ev > 0.05:
            consensus = "positive_ev"
        elif ev > 0:
            consensus = "marginal"
        else:
            consensus = "negative_ev"

        return {
            "consensus_score": round(confidence, 1),
            "consensus": consensus,
            "ev_adjustment": round(form_adjustment, 4),
            "resources_factors": {
                "home_form": resources.home_form,
                "away_form": resources.away_form,
                "rest_days_diff": resources.home_rest_days - resources.away_rest_days,
            }
        }