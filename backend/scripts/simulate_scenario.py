import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.db.session import SessionLocal
from app.api.routes.demo import trigger_scenario
from app.schemas.demo import DemoScenarioRequest

def main():
    parser = argparse.ArgumentParser(description="Simulate PayTrace payment scenario")
    parser.add_argument(
        "--scenario",
        default="timeout_before_response",
        choices=["timeout_before_response", "capture_denied", "duplicate_webhook_replay"],
        help="Scenario to simulate"
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        req = DemoScenarioRequest(scenario=args.scenario)
        res = trigger_scenario(req, db)
        print(f"Scenario Triggered: {res.title}")
        print(f"Payment ID: {res.payment_id}")
        print(f"Description: {res.description}")
        print(f"Details: {res.details}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
