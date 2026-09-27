"""Run every analysis in order and record how long each one takes.

    python3 scripts/run_all.py

Steps:
    1. Record the data file's fingerprint (size, modified time, SHA-256)
       BEFORE any analysis runs, so Analysis 6 can confirm nothing changed.
    2. Run Analyses 1-6 one after another, stopping if any of them fails.
    3. Write docs/results/run_log.csv with each script's runtime and status.
"""

import json
import subprocess
import sys
import time
from datetime import datetime

import pandas as pd

from dhs_utils import RESULTS_DIR, ROOT, dta_fingerprint

SCRIPTS = [
    "education_employment_summary.py",      # Analysis 1
    "education_employment_age.py",          # Analysis 2
    "education_employment_urban_rural.py",  # Analysis 3
    "education_employment_wealth.py",       # Analysis 4
    "state_comparison.py",                  # Analysis 5 (needs Analysis 1)
    "data_quality_checks.py",               # Analysis 6 (needs 1-5)
]


def main():
    fingerprint_path = RESULTS_DIR / "analysis_6" / "dta_fingerprint_before.json"
    fingerprint_path.parent.mkdir(parents=True, exist_ok=True)
    print("Recording data file fingerprint before running analyses...")
    before = dta_fingerprint()
    before["recorded_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fingerprint_path.write_text(json.dumps(before, indent=2))
    print(f"  size={before['size_bytes']:,} modified={before['modified']} sha256={before['sha256'][:16]}...")

    log = []
    for script in SCRIPTS:
        print(f"\n=== {script}")
        start = time.time()
        # Run each script as a separate Python process, exactly as if typed in a terminal.
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / script)],
                                capture_output=True, text=True)
        seconds = round(time.time() - start, 1)
        print(result.stdout, end="")
        if result.stderr:
            print("--- stderr (warnings/errors):\n" + result.stderr, end="")
        log.append({"script": script, "seconds": seconds, "exit_code": result.returncode,
                    "stderr_lines": len(result.stderr.splitlines())})
        if result.returncode != 0:
            print(f"\n{script} FAILED; stopping.")
            break

    log = pd.DataFrame(log)
    log.to_csv(RESULTS_DIR / "run_log.csv", index=False)
    print("\n" + log.to_string(index=False))
    print(f"total: {log.seconds.sum():.1f}s")
    sys.exit(int(log.exit_code.max()))


if __name__ == "__main__":
    main()
