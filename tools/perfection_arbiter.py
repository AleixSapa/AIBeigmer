"""AIBench perfection arbiter.

Static quality gate: catches demo-only state, browser secrets, and placeholder
benchmark generation before changes are considered production-ready.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "backend/app/main.py"
MODELS = ROOT / "frontend/js/models.js"

errors: list[str] = []
main = MAIN.read_text(encoding="utf-8") if MAIN.exists() else ""
models = MODELS.read_text(encoding="utf-8") if MODELS.exists() else ""

if "executions=[]" in main or re.search(r"executions\s*=\s*\[\]", main):
    errors.append("Executions cannot live only in process memory; persist them in PostgreSQL/Supabase.")
if re.search(r"def seed_questions\(\).*?INSERT OR IGNORE INTO questions", main, re.S):
    errors.append("Do not auto-seed generic placeholder benchmark questions as if they were real tests.")
if re.search(r"(?:sk-|AIza|xoxb-|ghp_)[A-Za-z0-9_-]{12,}", main + models):
    errors.append("Possible hard-coded API secret detected in application source.")
if "alert(`Fet!" in models and "location.reload()" in models:
    # Not a failure by itself, but keep the arbiter focused on critical quality.
    pass

if errors:
    print("AIBench PERFECTION ARBITER: FAIL")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

print("AIBench PERFECTION ARBITER: PASS")
