# ============================================================
# Group: XX | Date: 2026-03-16 | Members: Mounia, [partner]
# run.py — Headless simulation + chart
# ============================================================

from model import RobotMission
from agents import RobotAgent
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    model = RobotMission(
        width=15, height=10,
        n_green=4, n_yellow=2, n_red=2,
        n_wastes=20, seed=42,
    )

    for step in range(1, 301):
        model.step()

        if step % 50 == 0:
            data = model.datacollector.get_model_dataframe()
            g = data["Green Wastes"].iloc[-1]
            y = data["Yellow Wastes"].iloc[-1]
            r = data["Red Wastes"].iloc[-1]
            d = data["Disposed"].iloc[-1]
            inv = sum(len(a.inventory) for a in model.agents if isinstance(a, RobotAgent))
            print(f"Step {step:4d} | Grid: G={g} Y={y} R={r} | Carried: {inv} | Disposed: {d}")

            if g + y + r + inv == 0:
                print(f"\n*** All waste disposed at step {step}! ***")
                break

    # --- plot ---
    data = model.datacollector.get_model_dataframe()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    ax1.plot(data.index, data["Green Wastes"], "g-", label="Green")
    ax1.plot(data.index, data["Yellow Wastes"], color="#cccc00", label="Yellow")
    ax1.plot(data.index, data["Red Wastes"], "r-", label="Red")
    ax1.set_xlabel("Step")
    ax1.set_ylabel("Count on grid")
    ax1.set_title("Waste on the grid over time")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2.plot(data.index, data["Disposed"], "k-", linewidth=2)
    ax2.set_xlabel("Step")
    ax2.set_ylabel("Total disposed")
    ax2.set_title("Cumulative waste disposed")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig("simulation_results.png", dpi=150)
    print("\nChart saved to simulation_results.png")


if __name__ == "__main__":
    main()