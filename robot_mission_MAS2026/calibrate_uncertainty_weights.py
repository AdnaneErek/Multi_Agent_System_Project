import argparse
import csv
import random
import statistics
import time
from model import RobotMission


MAX_STEPS = 500

CONFIGS = [
    {"name": "C1_balanced_small", "n_green": 3, "n_yellow": 2, "n_red": 2, "n_wastes": 15},
    {"name": "C2_green_heavy", "n_green": 5, "n_yellow": 2, "n_red": 2, "n_wastes": 25},
    {"name": "C3_pipeline_strong", "n_green": 4, "n_yellow": 3, "n_red": 3, "n_wastes": 25},
    {"name": "C4_red_limited", "n_green": 4, "n_yellow": 2, "n_red": 1, "n_wastes": 20},
]

DEFAULT_WEIGHTS = {
    "radio_penalty_weight": 2.5,
    "crowd_penalty_weight": 1.5,
    "east_bonus_weight_regular": 0.60,
    "east_bonus_weight_red": 0.30,
    "scarcity_le2_bonus": 0.75,
    "scarcity_eq1_bonus": 1.25,
}

RANGES = {
    "radio_penalty_weight": (1.0, 4.0),
    "crowd_penalty_weight": (0.5, 2.5),
    "east_bonus_weight_regular": (0.2, 1.0),
    "east_bonus_weight_red": (0.1, 0.7),
    "scarcity_le2_bonus": (0.2, 1.6),
    "scarcity_eq1_bonus": (0.6, 2.2),
}


def run_one(config, seed, max_steps, weights):
    model = RobotMission(
        width=15,
        height=10,
        n_green=config["n_green"],
        n_yellow=config["n_yellow"],
        n_red=config["n_red"],
        n_wastes=config["n_wastes"],
        seed=seed,
        use_communication=True,
        use_orchestrator=True,
        use_uncertainty_scoring=True,
        orchestrator_weights=weights,
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
        "completed": completed,
        "steps_executed": steps_executed,
        "remaining_total": remaining["green"] + remaining["yellow"] + remaining["red"],
        "messages_total": model.total_messages_sent,
    }


def evaluate_candidate(weights, seeds, base_seed, max_steps):
    rows = []
    for cfg_idx, config in enumerate(CONFIGS):
        config_seed_start = base_seed + cfg_idx * 1000
        for seed_offset in range(seeds):
            seed = config_seed_start + seed_offset
            row = run_one(config, seed, max_steps, weights)
            rows.append(row)

    n = len(rows)
    completion_rate = sum(1 for r in rows if r["completed"]) / n
    steps_mean = statistics.mean(r["steps_executed"] for r in rows)
    remaining_mean = statistics.mean(r["remaining_total"] for r in rows)
    messages_mean = statistics.mean(r["messages_total"] for r in rows)

    # Priority: completion, then leftovers, then speed, then communication cost.
    objective = (
        (1.0 - completion_rate) * 1000.0
        + remaining_mean * 25.0
        + steps_mean
        + messages_mean / 1000.0
    )

    return {
        "completion_rate": completion_rate,
        "steps_mean": steps_mean,
        "remaining_mean": remaining_mean,
        "messages_mean": messages_mean,
        "objective": objective,
    }


def sample_candidate(rng):
    candidate = {}
    for key, (low, high) in RANGES.items():
        candidate[key] = round(rng.uniform(low, high), 3)

    # keep scarcity==1 bonus at least scarcity<=2 bonus
    candidate["scarcity_eq1_bonus"] = round(
        max(candidate["scarcity_eq1_bonus"], candidate["scarcity_le2_bonus"]), 3
    )
    return candidate


def save_candidates(rows, output_file):
    if not rows:
        return

    fieldnames = [
        "rank",
        "objective",
        "completion_rate",
        "steps_mean",
        "remaining_mean",
        "messages_mean",
        "radio_penalty_weight",
        "crowd_penalty_weight",
        "east_bonus_weight_regular",
        "east_bonus_weight_red",
        "scarcity_le2_bonus",
        "scarcity_eq1_bonus",
    ]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Calibrate uncertainty-scoring weights for Step 3 orchestrator."
    )
    parser.add_argument("--seeds", type=int, default=10, help="Seeds per config (default: 10)")
    parser.add_argument("--base-seed", type=int, default=100, help="Base seed (default: 100)")
    parser.add_argument("--max-steps", type=int, default=MAX_STEPS, help="Max steps (default: 500)")
    parser.add_argument("--trials", type=int, default=40, help="Number of random candidates (default: 40)")
    parser.add_argument("--search-seed", type=int, default=2026, help="Random seed for search (default: 2026)")
    parser.add_argument(
        "--output",
        default="uncertainty_weight_calibration.csv",
        help="Output CSV for ranked candidates",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    rng = random.Random(args.search_seed)
    t0 = time.perf_counter()

    candidates = [DEFAULT_WEIGHTS]
    seen = {tuple(sorted(DEFAULT_WEIGHTS.items()))}

    while len(candidates) < args.trials + 1:
        c = sample_candidate(rng)
        key = tuple(sorted(c.items()))
        if key in seen:
            continue
        seen.add(key)
        candidates.append(c)

    scored = []
    for idx, weights in enumerate(candidates, start=1):
        trial_t0 = time.perf_counter()
        metrics = evaluate_candidate(weights, args.seeds, args.base_seed, args.max_steps)
        row = {"rank": 0, **metrics, **weights}
        scored.append(row)
        trial_elapsed = time.perf_counter() - trial_t0
        total_elapsed = time.perf_counter() - t0
        print(
            f"[{idx}/{len(candidates)}] objective={metrics['objective']:.3f} "
            f"completion={metrics['completion_rate'] * 100:.1f}% "
            f"steps={metrics['steps_mean']:.1f} "
            f"trial_s={trial_elapsed:.1f} total_s={total_elapsed:.1f}",
            flush=True,
        )

    scored.sort(key=lambda r: (r["objective"], -r["completion_rate"], r["steps_mean"]))
    for i, row in enumerate(scored, start=1):
        row["rank"] = i

    save_candidates(scored, args.output)

    best = scored[0]
    print("\n=== Best calibrated weights ===")
    print(f"Objective: {best['objective']:.3f}")
    print(f"Completion rate: {best['completion_rate'] * 100:.2f}%")
    print(f"Mean steps: {best['steps_mean']:.2f}")
    print(f"Mean remaining: {best['remaining_mean']:.3f}")
    print(f"Mean messages: {best['messages_mean']:.2f}")
    print(
        "Weights: "
        f"radio={best['radio_penalty_weight']}, "
        f"crowd={best['crowd_penalty_weight']}, "
        f"east_regular={best['east_bonus_weight_regular']}, "
        f"east_red={best['east_bonus_weight_red']}, "
        f"scarcity_le2={best['scarcity_le2_bonus']}, "
        f"scarcity_eq1={best['scarcity_eq1_bonus']}"
    )
    print(f"\nSaved ranked candidates to {args.output}")


if __name__ == "__main__":
    main()
