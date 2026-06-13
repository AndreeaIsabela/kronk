import json
import os

TIMERS_FILE = os.path.join(os.path.dirname(__file__), "timers.json")


def load_timers() -> dict:
    if not os.path.exists(TIMERS_FILE):
        return {}
    with open(TIMERS_FILE, "r") as f:
        return json.load(f)


def save_timers(data: dict) -> None:
    with open(TIMERS_FILE, "w") as f:
        json.dump(data, f, indent=2)
