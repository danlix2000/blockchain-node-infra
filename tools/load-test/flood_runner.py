#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
import re
import csv
from typing import Dict, List, Optional

TABLE_NAME_RE = re.compile(r"^\s*│\s*(.+?)\s*│\s*$")


def run(cmd: List[str], ignore_errors: bool = False) -> Optional[str]:
    print("\n$ " + " ".join(cmd))
    p = subprocess.run(cmd, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        print(f"[WARN] Command exited with status {p.returncode}")
        if p.stdout:
            print(p.stdout[-500:])  # last 500 chars of output for context
        if not ignore_errors:
            return None
    return p.stdout


def parse_tables(text: str) -> Dict[str, Dict[int, float]]:
    """
    Parses flood's console tables like:
      success vs load / throughput vs load / p90 vs load / p99 vs load
    into {table_name: {rate: value}}
    """
    tables: Dict[str, Dict[int, float]] = {}
    current: Optional[str] = None

    for line in text.splitlines():
        m = TABLE_NAME_RE.match(line.strip())
        if m and "vs load" in m.group(1):
            current = m.group(1).strip()
            tables.setdefault(current, {})
            continue

        if current:
            m2 = re.search(r"^\s*(\d+)\s*│\s*([0-9.]+)", line)
            if m2:
                rate = int(m2.group(1))
                val = float(m2.group(2))
                tables[current][rate] = val

    return tables


def write_summary(rows: List[dict], session_dir: Path, run_id: str) -> None:
    """Write summary.csv and summary.md. Called after each test for incremental output."""
    if not rows:
        return
    csv_path = session_dir / "summary.csv"
    md_path = session_dir / "summary.md"

    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    with md_path.open("w") as f:
        f.write(f"# Flood summary {run_id}\n\n")
        f.write(f"- Session dir: `{session_dir}`\n\n")
        f.write(
            "| node | kind | test | rate | success% | thrpt(rps) | p90(s) | p99(s) |\n")
        f.write("|---|---|---|---:|---:|---:|---:|---:|\n")
        for row in rows:
            f.write(
                f"| {row['node']} | {row['kind']} | {row['test']} | {row['rate_rps']} | "
                f"{row['success_pct']} | {row['throughput_rps']} | {row['p90_s']} | {row['p99_s']} |\n"
            )


def build_flood_cmd(image: str, out_dir_host: Path, test: str, node_spec: str,
                    rates: List[int], duration: int, metrics: List[str],
                    deep_check: bool, vegeta_args: Optional[str],
                    network_mode: str, seed: Optional[int] = None,
                    dry: bool = False) -> List[str]:
    cmd = ["docker", "run", "--rm"]
    if network_mode:
        cmd += ["--network", network_mode]

    cmd += ["-v", f"{out_dir_host}:/out", image, test]
    cmd += node_spec.split()
    cmd += ["--rates"] + [str(r) for r in rates]
    cmd += ["--duration", str(duration)]
    cmd += ["--output", "/out"]
    cmd += ["--metrics"] + metrics
    if deep_check:
        cmd += ["--deep-check"]
    if vegeta_args:
        cmd += [f'--vegeta-args={vegeta_args}']
    if seed is not None:
        cmd += ["--seed", str(seed)]
    if dry:
        cmd += ["--dry"]
    return cmd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", default="nodes.json")
    ap.add_argument("--suites", default="suites.json")
    ap.add_argument("--out", default="flood_out")
    ap.add_argument("--image", default="ghcr.io/paradigmxyz/flood:0.3.1")
    ap.add_argument("--network", default="",
                    help="use 'host' if targeting localhost from docker")
    ap.add_argument("--kinds", default="",
                    help="comma list: full,archive (default: all)")
    ap.add_argument("--node", default="",
                    help="comma list of node names to run (default: all)")
    ap.add_argument("--tests", default="",
                    help="comma list of test names to run (default: all in suite)")
    ap.add_argument("--report", action="store_true",
                    help="run flood report after each test")
    ap.add_argument("--seed", type=int, default=None,
                    help="random seed for reproducible tests")
    ap.add_argument("--dry", action="store_true",
                    help="preview tests without running them")
    args = ap.parse_args()

    nodes = json.loads(Path(args.nodes).read_text())["nodes"]
    suites = json.loads(Path(args.suites).read_text())["suites"]

    kinds_filter = {k.strip()
                    for k in args.kinds.split(",") if k.strip()} or None
    node_filter = {k.strip()
                   for k in args.node.split(",") if k.strip()} or None
    tests_filter = {k.strip()
                    for k in args.tests.split(",") if k.strip()} or None

    base_out = Path(args.out).resolve()
    run_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = base_out / f"session_{run_id}"
    session_dir.mkdir(parents=True, exist_ok=True)

    rows = []

    for n in nodes:
        kind = n["kind"]
        node_name = n["name"]
        if kinds_filter and kind not in kinds_filter:
            continue
        if node_filter and node_name not in node_filter:
            continue
        node_spec = n["spec"]

        suite = suites[kind]
        common = suite.get("common", {})
        common_duration = int(common.get("duration", 30))
        common_metrics = common.get(
            "metrics", ["success", "throughput", "p90"])
        common_vegeta_args = common.get("vegeta_args")
        common_deep = bool(common.get("deep_check", False))

        for t in suite["tests"]:
            test = t["test"]
            if tests_filter and test not in tests_filter:
                continue
            rates = t["rates"]
            duration = int(t.get("duration", common_duration))
            metrics = t.get("metrics", common_metrics)
            deep_check = bool(t.get("deep_check", common_deep))
            vegeta_args = t.get("vegeta_args", common_vegeta_args)

            out_dir = session_dir / node_name / test
            out_dir.mkdir(parents=True, exist_ok=True)

            # 1) run the test
            cmd = build_flood_cmd(args.image, out_dir, test, node_spec, rates,
                                  duration, metrics, deep_check, vegeta_args,
                                  args.network, seed=args.seed, dry=args.dry)
            result = run(cmd)

            if args.dry:
                continue

            if result is None:
                print(f"[SKIP] {node_name}/{test} - test failed, skipping results collection")
                for r in rates:
                    rows.append({
                        "session": run_id,
                        "node": node_name,
                        "kind": kind,
                        "test": test,
                        "rate_rps": r,
                        "success_pct": "FAILED",
                        "throughput_rps": None,
                        "p90_s": None,
                        "p99_s": None,
                        "output_dir": str(out_dir),
                    })
                write_summary(rows, session_dir, run_id)
                continue

            # 2) re-print results (stable format) and save summary.txt
            printed = run(["docker", "run", "--rm", "-v", f"{out_dir}:/out",
                           args.image, "print", "/out", "--metrics", *metrics])
            if printed is None:
                printed = result  # fallback to original output
            (out_dir / "summary.txt").write_text(printed)

            tables = parse_tables(printed)
            success = tables.get("success vs load", {})
            thrpt = tables.get("throughput vs load", {})
            p90 = tables.get("p90 vs load", {})
            p99 = tables.get("p99 vs load", {})

            for r in rates:
                rows.append({
                    "session": run_id,
                    "node": node_name,
                    "kind": kind,
                    "test": test,
                    "rate_rps": r,
                    "success_pct": success.get(r),
                    "throughput_rps": thrpt.get(r),
                    "p90_s": p90.get(r),
                    "p99_s": p99.get(r),
                    "output_dir": str(out_dir),
                })

            # 3) write summary after each test (incremental - survives interruptions)
            write_summary(rows, session_dir, run_id)

            # 4) optional report generation
            if args.report:
                run(["docker", "run", "--rm", "-v", f"{out_dir}:/out",
                     args.image, "report", "/out"])

    csv_path = session_dir / "summary.csv"
    md_path = session_dir / "summary.md"
    print(f"\nDone.\nSession: {session_dir}\nCSV: {csv_path}\nMD: {md_path}")


if __name__ == "__main__":
    main()
