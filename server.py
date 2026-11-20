"""
ApexQuant — 5-Agent AI Prediction Server
=========================================

Flask backend that:
  1. Serves the frontend (apexquant.html as index.html)
  2. Exposes /api/refresh-matches endpoint
  3. Runs all matches through the 5-Agent AI Council
  4. Returns rich predictions with agent breakdowns

Run with:
    python server.py

Then open: http://127.0.0.1:5000

Set API keys in the same terminal:
    $env:ODDS_API_KEY="your_key_here"   # PowerShell
    set ODDS_API_KEY=your_key_here      # CMD
"""

import os
import traceback
from flask import Flask, jsonify, send_from_directory, request

from live_data_fetcher import LiveDataFetcher
from ai_agents import analyze_matches, get_top_picks, ConsensusResult

# ──────────────────────────────────────────────────────────
#  Flask app setup
# ──────────────────────────────────────────────────────────

app = Flask(__name__, static_folder=".", static_url_path="")
fetcher = LiveDataFetcher()

# In-memory cache for latest predictions
_latest_predictions = []
_latest_raw_matches = []


# ──────────────────────────────────────────────────────────
#  Routes
# ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the main frontend page with the API key injected from env var."""
    key = os.getenv("ODDS_API_KEY", "")
    # Read the HTML file and inject the API key
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "apexquant.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Inject the API key as a global JS variable before the closing </head>
    injection = f'<script>window.__ODDS_API_KEY__ = "{key}";</script>'
    html = html.replace("</head>", injection + "</head>", 1)

    return html


@app.route("/api/refresh-matches", methods=["POST", "GET"])
def refresh_matches():
    """
    Fetch real matches from APIs, run through 5-Agent AI Council,
    return enriched predictions with agent breakdowns.

    Response structure:
    {
      "success": true,
      "count": 24,
      "matches_by_date": {
        "2026-10-29": [
          {
            "match_id": "...",
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "league": "Premier League",
            "match_time": "17:30",
            "odds": {...},
            "consensus": {
              "home_win_prob": 0.52,
              "draw_prob": 0.26,
              "away_win_prob": 0.22,
              "predicted_score": "2-1",
              "confidence": 7.8,
              "top_pick": "home_win",
              "top_pick_odds": 2.10,
              "ev": 0.092,
              "reasoning": "...",
              "agent_votes": {...}
            },
            "agents": [
              {
                "name": "STATS_ANALYST",
                "label": "Statistical Model",
                "home_win_prob": 0.55,
                "draw_prob": 0.25,
                "away_win_prob": 0.20,
                "predicted_home_goals": 1.8,
                "predicted_away_goals": 1.2,
                "confidence": 7.2,
                "reasoning": "...",
                "metadata": {...}
              },
              ...
            ]
          }
        ]
      },
      "top_picks": [...]  # top 8 by confidence
    }
    """
    global _latest_predictions, _latest_raw_matches

    try:
        # Step 1: Fetch real matches from APIs
        matches_by_date = fetcher.get_live_matches(days_ahead=3)

        if not matches_by_date:
            return jsonify({
                "success": False,
                "error": (
                    "No matches returned. Check that ODDS_API_KEY is set "
                    "correctly in the terminal running this server, and "
                    "that your API key is active. Running with demo data."
                ),
                "demo_mode": True,
            }), 200

        # Step 2: Flatten matches for AI analysis
        all_matches = []
        for date, match_list in matches_by_date.items():
            for m in match_list:
                # Ensure required fields for ai_agents
                match_data = {
                    "id": m.get("id", f"{m.get('home_team', 'H')}-{m.get('away_team', 'A')}"),
                    "home_team": m.get("home_team", "Home"),
                    "away_team": m.get("away_team", "Away"),
                    "league": m.get("league", "Unknown"),
                    "match_date": m.get("match_date", date),
                    "match_time": m.get("match_time", "TBA"),
                    "odds": m.get("odds", {}),
                    "home_elo": m.get("home_elo", 1500),
                    "away_elo": m.get("away_elo", 1500),
                }
                all_matches.append(match_data)

        _latest_raw_matches = all_matches

        # Step 3: Run through 5-Agent AI Council
        results = analyze_matches(all_matches)

        # Step 4: Organize results by date
        results_by_date = {}
        for date, match_list in matches_by_date.items():
            date_results = []
            for m in match_list:
                mid = m.get("id", f"{m.get('home_team', 'H')}-{m.get('away_team', 'A')}")
                for r in results:
                    if r.match_id == mid:
                        date_results.append(_serialize_result(r, m))
                        break
            if date_results:
                results_by_date[date] = date_results

        # Step 5: Get top picks
        top_picks = get_top_picks(all_matches, min_confidence=6.0, top_n=8)
        top_picks_serialized = [_serialize_result(p, {}) for p in top_picks]

        _latest_predictions = results

        return jsonify({
            "success": True,
            "count": len(all_matches),
            "matches_by_date": results_by_date,
            "top_picks": top_picks_serialized,
            "leagues_covered": len(set(m.get("league", "") for m in all_matches)),
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@app.route("/api/top-picks", methods=["GET"])
def get_top_picks_endpoint():
    """Return top 8 picks from the latest cached predictions."""
    global _latest_predictions

    if not _latest_predictions:
        return jsonify({
            "success": False,
            "message": "No predictions cached. Call /api/refresh-matches first.",
        }), 404

    top_picks = sorted(_latest_predictions, key=lambda r: r.confidence, reverse=True)[:8]
    return jsonify({
        "success": True,
        "picks": [_serialize_result(p, {}) for p in top_picks],
    }), 200


@app.route("/api/match/<match_id>", methods=["GET"])
def get_match_detail(match_id):
    """Get detailed breakdown for a single match."""
    global _latest_predictions

    for r in _latest_predictions:
        if r.match_id == match_id:
            # Find original match data
            orig = {}
            for m in _latest_raw_matches:
                if m.get("id") == match_id:
                    orig = m
                    break
            return jsonify({
                "success": True,
                "match": _serialize_result(r, orig),
            }), 200

    return jsonify({
        "success": False,
        "error": f"Match {match_id} not found",
    }), 404


# ──────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────

def _serialize_result(result: ConsensusResult, original_match: dict) -> dict:
    """Convert ConsensusResult to JSON-serializable dict."""
    return {
        "match_id": result.match_id,
        "home_team": result.home_team,
        "away_team": result.away_team,
        "league": result.league,
        "match_time": result.match_time,
        "match_date": original_match.get("match_date", ""),
        "venue": original_match.get("venue", "TBA"),
        "odds": original_match.get("odds", {}),
        "consensus": {
            "home_win_prob": result.home_win_prob,
            "draw_prob": result.draw_prob,
            "away_win_prob": result.away_win_prob,
            "predicted_score": result.predicted_score,
            "confidence": result.confidence,
            "top_pick": result.top_pick,
            "top_pick_odds": result.top_pick_odds,
            "ev": result.ev,
            "reasoning": result.reasoning,
            "agent_votes": result.agent_votes,
        },
        "agents": [
            {
                "name": p.agent_name,
                "label": p.agent_label,
                "home_win_prob": p.home_win_prob,
                "draw_prob": p.draw_prob,
                "away_win_prob": p.away_win_prob,
                "predicted_home_goals": p.predicted_home_goals,
                "predicted_away_goals": p.predicted_away_goals,
                "confidence": p.confidence,
                "reasoning": p.reasoning,
                "suggested_bet": p.suggested_bet,
                "suggested_odds": p.suggested_odds,
                "ev": p.ev,
                "metadata": p.metadata,
            }
            for p in result.agent_predictions
        ],
    }


# ──────────────────────────────────────────────────────────
#  Main entry point
# ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    key_set = bool(os.getenv("ODDS_API_KEY")) or bool(os.getenv("FOOTBALL_API_KEY"))

    print("=" * 70)
    print("⚽ APEXQUANT — 5-AGENT AI PREDICTION SERVER")
    print("=" * 70)

    if not key_set:
        print("⚠️  WARNING: No API key detected. Set ODDS_API_KEY for real data:")
        print("    PowerShell: $env:ODDS_API_KEY=\"your_key_here\"")
        print("    CMD:        set ODDS_API_KEY=your_key_here")
        print()
        print("Server will start in DEMO mode with simulated matches.")
        print()

    port = int(os.environ.get("PORT", 5000))
    print(f"Starting ApexQuant backend server on port {port}...")
    print(f"Open http://127.0.0.1:{port} in your browser once running.")
    print()
    print("API Endpoints:")
    print("  POST /api/refresh-matches  — Fetch matches + run 5-agent AI analysis")
    print("  GET  /api/top-picks        — Get top 8 picks from cache")
    print("  GET  /api/match/<id>       — Get detailed breakdown for one match")
    print("=" * 70)

    app.run(debug=False, port=port)
