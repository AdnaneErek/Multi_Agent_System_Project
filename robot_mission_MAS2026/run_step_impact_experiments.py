# ============================================================
# run_step_impact_experiments.py — Compare Step 1 vs Step 2 vs Step 3
# ============================================================

import argparse
import csv
import statistics
from model import RobotMission


MAX_STEPS = 500

# 4 requested configurations (robots + initial green wastes)
CONFIGS = [
    {"name": "C1_balanced_small", "n_green": 3, "n_yellow": 2, "n_red": 2, "n_wastes": 15},
    {"name": "C2_green_heavy", "n_green": 5, "n_yellow": 2, "n_red": 2, "n_wastes": 25},
    {"name": "C3_pipeline_strong", "n_green": 4, "n_yellow": 3, "n_red": 3, "n_wastes": 25},
    {"name": "C4_red_limited", "n_green": 4, "n_yellow": 2, "n_red": 1, "n_wastes": 20},
]

MODES = [
    {
        "mode": "step1_no_communication",
        "use_communication": False,
        "use_orchestrator": False,
    },
    {
        "mode": "step2_communication",
        "use_communication": True,
        "use_orchestrator": False,
    },
    {
        "mode": "step3_orchestrator",
        "use_communication": True,
        "use_orchestrator": True,
    },
]


def run_one(config, mode, seed, max_steps=MAX_STEPS):
    model = RobotMission(
        width=15,
        height=10,
        n_green=config["n_green"],
        n_yellow=config["n_yellow"],
        n_red=config["n_red"],
        n_wastes=config["n_wastes"],
        seed=seed,
        use_communication=mode["use_communication"],
        use_orchestrator=mode["use_orchestrator"],
    )

    completed = False
    steps_executed = 0

    for step in range(1, max_steps + 1):
        model.step()
        steps_executed = step
        if not getattr(model, "running", True):
            completed = True
            break

    remaining = model.remaining_waste_counts()

    return {
        "config": config["name"],
        "mode": mode["mode"],
        "seed": seed,
        "completed": completed,
        "steps_executed": steps_executed,
        "diverged": not completed,
        "disposed": model.disposed_count,
        "remaining_green": remaining["green"],
        "remaining_yellow": remaining["yellow"],
        "remaining_red": remaining["red"],
        "remaining_total": remaining["green"] + remaining["yellow"] + remaining["red"],
        "messages_total": model.total_messages_sent,
    }


def print_results_table(results):
    header = (
        f"{'Config':<20} {'Mode':<24} {'Done':<6} {'Steps':<7} "
        f"{'Disposed':<9} {'Remaining':<10} {'Messages':<9}"
    )
    print(header)
    print("-" * len(header))

    for r in results:
        print(
            f"{r['config']:<20} {r['mode']:<24} "
            f"{str(r['completed']):<6} {r['steps_executed']:<7} "
            f"{r['disposed']:<9} {r['remaining_total']:<10} {r['messages_total']:<9}"
        )


def save_csv(results, output_file="step_impact_results.csv"):
    fieldnames = [
        "config",
        "mode",
        "seed",
        "completed",
        "steps_executed",
        "diverged",
        "disposed",
        "remaining_green",
        "remaining_yellow",
        "remaining_red",
        "remaining_total",
        "messages_total",
    ]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nSaved results to {output_file}")


def aggregate_results(results):
    grouped = {}
    for r in results:
        key = (r["config"], r["mode"])
        grouped.setdefault(key, []).append(r)

    summary_rows = []
    for (config_name, mode_name), rows in grouped.items():
        n = len(rows)

        steps = [r["steps_executed"] for r in rows]
        disposed = [r["disposed"] for r in rows]
        remaining = [r["remaining_total"] for r in rows]
        messages = [r["messages_total"] for r in rows]
        completed_count = sum(1 for r in rows if r["completed"])
        diverged_count = n - completed_count

        summary_rows.append({
            "config": config_name,
            "mode": mode_name,
            "runs": n,
            "completed_count": completed_count,
            "diverged_count": diverged_count,
            "completion_rate_pct": 100.0 * completed_count / n,
            "steps_mean": statistics.mean(steps),
            "steps_stdev": statistics.stdev(steps) if n > 1 else 0.0,
            "disposed_mean": statistics.mean(disposed),
            "disposed_stdev": statistics.stdev(disposed) if n > 1 else 0.0,
            "remaining_mean": statistics.mean(remaining),
            "remaining_stdev": statistics.stdev(remaining) if n > 1 else 0.0,
            "messages_mean": statistics.mean(messages),
            "messages_stdev": statistics.stdev(messages) if n > 1 else 0.0,
        })

    summary_rows.sort(key=lambda x: (x["config"], x["mode"]))
    return summary_rows


def save_summary_csv(summary_rows, output_file="step_impact_summary.csv"):
    fieldnames = [
        "config",
        "mode",
        "runs",
        "completed_count",
        "diverged_count",
        "completion_rate_pct",
        "steps_mean",
        "steps_stdev",
        "disposed_mean",
        "disposed_stdev",
        "remaining_mean",
        "remaining_stdev",
        "messages_mean",
        "messages_stdev",
    ]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"Saved summary to {output_file}")


def print_summary_table(summary_rows):
    header = (
        f"{'Config':<20} {'Mode':<24} {'Runs':<5} {'Done%':<8} "
        f"{'Steps mean±std':<21} {'Remaining mean±std':<23} {'Messages mean±std':<22}"
    )
    print(header)
    print("-" * len(header))

    for r in summary_rows:
        steps_text = f"{r['steps_mean']:.1f}±{r['steps_stdev']:.1f}"
        rem_text = f"{r['remaining_mean']:.2f}±{r['remaining_stdev']:.2f}"
        msg_text = f"{r['messages_mean']:.1f}±{r['messages_stdev']:.1f}"
        print(
            f"{r['config']:<20} {r['mode']:<24} {r['runs']:<5} "
            f"{r['completion_rate_pct']:<8.1f} {steps_text:<21} {rem_text:<23} {msg_text:<22}"
        )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run Step 1/2/3 impact experiments on multiple configurations and seeds."
    )
    parser.add_argument(
        "--seeds",
        type=int,
        default=20,
        help="Number of seeds per configuration (default: 20).",
    )
    parser.add_argument(
        "--base-seed",
        type=int,
        default=100,
        help="Starting seed value (default: 100).",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=MAX_STEPS,
        help=f"Maximum steps per run (default: {MAX_STEPS}).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    results = []

    for config_index, config in enumerate(CONFIGS):
        print(f"\n=== {config['name']} ===")
        config_seed_start = args.base_seed + config_index * 1000

        for seed_offset in range(args.seeds):
            seed = config_seed_start + seed_offset

            for mode in MODES:
                result = run_one(config, mode, seed=seed, max_steps=args.max_steps)
                results.append(result)

        # quick per-config completion snapshot
        for mode in MODES:
            mode_rows = [
                r for r in results
                if r["config"] == config["name"] and r["mode"] == mode["mode"]
            ]
            completed_count = sum(1 for r in mode_rows if r["completed"])
            print(
                f"{mode['mode']}: completed {completed_count}/{len(mode_rows)} runs"
            )

    print("\n=== Detailed single-run table ===")
    print_results_table(results)
    save_csv(results)

    summary_rows = aggregate_results(results)
    print("\n=== Multi-seed summary (mean ± std) ===")
    print_summary_table(summary_rows)
    save_summary_csv(summary_rows)


if __name__ == "__main__":
    main()
