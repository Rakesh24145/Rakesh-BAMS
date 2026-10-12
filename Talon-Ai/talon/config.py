"""Fixed settings. (AI-engine choices live in settings.py and the Settings page.)"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("TALON_DATA", BASE_DIR / "data"))
DB_PATH = Path(os.getenv("TALON_DB", DATA_DIR / "talon.db"))
KNOWLEDGE_DIR = BASE_DIR / "knowledge"            # your own .txt / .md files
SAMPLE_DIR = BASE_DIR / "sample_data"
WEB_DIR = BASE_DIR / "web"

AGENT_MAX_STEPS = 3                               # max tool calls per agent run
EST_CLOUD_COST_PER_1K_TOKENS = 0.002              # LEDGER: rough cloud-equivalent cost
MIN_SECONDS_PER_QUESTION = 4                      # SENTINEL: faster = suspicious
CODING_TIMEOUT_SECONDS = 5                        # TITAN: time limit for candidate code
SLA_HOURS_FOR_APPROVAL = 24                       # ATLAS: approval waiting longer = breach
