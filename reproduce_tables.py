"""Reproduce article Tables 1-5 and every numerical export used in Results."""
import hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
EXPORTS = [
    "absolute_metric_intervals.json", "cohort_comparison.csv",
    "main_metrics_all_conditions.csv", "paired_model_differences.csv",
    "per_run_metrics.csv", "robustness_changes.csv", "source_group_errors.csv",
    "threshold_sensitivity.csv", "unseen_confusion_counts.csv",
    "processing_transitions.csv", "prose_details.json",
]
with tempfile.TemporaryDirectory(prefix="rmt-reproduce-") as directory:
    copy = Path(directory) / "project"
    shutil.copytree(PROJECT, copy, ignore=shutil.ignore_patterns(
        ".git", "cache", "__pycache__", "*.pt", "*.pth", "main.pdf", "exports"))
    environment = os.environ.copy()
    for variable in ("PILOT_WORK", "ARTICLE_IMAGE_DIR"):
        environment.pop(variable, None)
    environment["ARTICLE_SCORES_ONLY"] = "1"
    for script in ("analyze.py", "report_error_transitions.py",
                   "report_prose_details.py", "write_tables.py"):
        subprocess.run([sys.executable, str(copy / "article" / script)],
                       env=environment, check=True, stdout=subprocess.DEVNULL)
    tables, exports = {}, {}
    def compare(relative):
        expected = (PROJECT / relative).read_bytes()
        actual = (copy / relative).read_bytes()
        if expected != actual:
            raise SystemExit(f"Reproduction mismatch: {relative}")
        return dict(status="exact match", sha256=hashlib.sha256(actual).hexdigest())
    for number, filename in [(1, "dataset.tex"), (2, "main_results.tex"),
                             (3, "paired.tex"), (4, "robustness.tex"),
                             (5, "sensitivity.tex")]:
        tables[str(number)] = compare(Path("tables") / filename)
        print(f"Table {number}: exact match")
    for filename in EXPORTS:
        exports[filename] = compare(Path("article/evaluation") / filename)
        print(f"Export {filename}: exact match")
    record = dict(method="Regenerated from saved scores, manifests and validation history "
                         "in an isolated temporary copy; no images, weights or network",
                  tables=tables, numerical_exports=exports)
    (PROJECT / "article/reproduction_check.json").write_text(
        json.dumps(record, indent=2) + "\n")
print("Tables 1-5 and all 11 numerical exports reproduced exactly.")
