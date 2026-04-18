# Robot Waste Cleanup Mission (MAS 2026)

## Overview

This project implements a **multi-agent simulation** of robots cleaning dangerous waste in a hostile environment. The environment is divided into three radioactivity zones from west to east, and the robots must collectively:

1. collect **green waste** in zone `z1`,
2. transform it into **yellow waste**,
3. transform yellow waste into **red waste**,
4. transport the final red waste to a **waste disposal cell** located in the easternmost column.

The project matches the assignment specification for the *Self-organization of robots in a hostile environment* practical work, which asks for:
- three waste types and three robot types,
- a grid-based environment with radioactivity levels,
- an agent loop based on **percepts → deliberate → do**,
- a first step without communication and a second step with communication,
- data extraction and visualization. 

## Quick start

From the repository root:

### Windows (PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cd robot_mission_MAS2026
solara run server.py
```

### Linux / macOS
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cd robot_mission_MAS2026
solara run server.py
```

Headless run (chart output):
```bash
cd robot_mission_MAS2026
python run.py
```

Step impact experiment (Step 1 vs Step 2 vs Step 3 + Step 3 ablation):
```bash
cd robot_mission_MAS2026
python run_step_impact_experiments.py
```

Optional multi-seed controls:
```bash
python run_step_impact_experiments.py --seeds 20 --base-seed 100 --max-steps 500
```

## Project structure

```text
.
├── README.md
└── robot_mission_MAS2026/
  ├── agents.py     # Robot agents, knowledge base, deliberation, navigation, communication use
  ├── model.py      # RobotMission model, grid, action execution, message board, data collection
  ├── objects.py    # Passive environment objects: radioactivity, waste, disposal zone
  ├── server.py     # Mesa/Solara visualization
  └── run.py        # Headless execution + result plots
```

## Simulation logic

### Environment
The model uses a `MultiGrid` environment split into three horizontal zones along the x-axis:
- **Zone 1 (`z1`)**: low radioactivity, contains the initial green wastes
- **Zone 2 (`z2`)**: medium radioactivity
- **Zone 3 (`z3`)**: high radioactivity, contains the final disposal area

Each grid cell contains a passive `Radioactivity` agent whose value is randomly assigned according to the zone:
- `z1`: between `0.0` and `0.33`
- `z2`: between `0.33` and `0.66`
- `z3`: between `0.66` and `1.0`

A `WasteDisposal` agent is placed at a random y-position in the easternmost column.

### Robots
There are three robot classes:

- **GreenAgent**
  - can only move in zone 1
  - picks up green waste
  - transforms 2 green wastes into 1 yellow waste
  - carries yellow waste eastward and drops it when it can no longer move further east

- **YellowAgent**
  - can move in zones 1 and 2
  - picks up yellow waste
  - transforms 2 yellow wastes into 1 red waste
  - carries red waste eastward and drops it when blocked by zone constraints

- **RedAgent**
  - can move in zones 1, 2, and 3
  - picks up red waste
  - transports red waste to the disposal zone
  - disposes of the waste permanently when standing on the disposal cell

### Perception and decision
Each robot follows the required MAS loop:

```python
percepts = self.model.get_percepts(self)
self._update_knowledge(percepts)
self._read_messages()
action = self.deliberate(self.knowledge)
new_percepts = self.model.do(self, action)
self._update_knowledge(new_percepts)
```

The local perception is a dictionary of adjacent cells using a Von Neumann neighborhood (current cell + four orthogonal neighbors).

### Knowledge representation
Each robot maintains a local knowledge base with:
- current position and current zone,
- current percepts,
- inventory,
- discovered zone map,
- known waste locations,
- visited cells,
- disposal location when discovered,
- current target,
- last message read step.

This makes the agents **stateful** rather than purely reactive.

## Communication design

The project implements a shared message board in the environment.

### Communication mechanism
The model stores messages in `self.message_board`. Each message contains:
- message type,
- sender id,
- position,
- optional waste color,
- simulation step.

Messages have a finite lifetime controlled by a **TTL of 50 steps**, after which they are removed.

### Message types
Three message types are implemented:
- `waste_picked`: a robot informs others that waste has disappeared from a cell
- `waste_dropped`: a robot informs others that waste has been dropped at a cell
- `disposal_found`: a robot broadcasts the disposal location once discovered

### Why this design?
This choice is simple, modular, and easy to debug. It avoids direct agent-to-agent coupling and respects the assignment spirit: agents reason from their own knowledge and percepts, while communication enriches that knowledge instead of replacing it.

## Recent improvements 

The following practical improvements were added to make the simulation more robust and easier to monitor:

### 1) Deadlock handling for Green/Yellow robots
- Added a **rendezvous strategy** for `GreenAgent` and `YellowAgent` when each robot may be stuck carrying one item with no matching item nearby.
- If a robot holds exactly one required waste and no other same-color waste is known, it moves to a shared meeting point and drops it for consolidation.
- Added a short **anti-repickup cooldown** to avoid immediate pick-drop loops.

### 2) Deterministic conflict resolution at rendezvous
- At rendezvous cells, only the same-type robot with the **lowest `unique_id`** is allowed to pick first.
- This removes nondeterministic contention and reduces oscillations.

### 3) Red robot singleton fallback rule
- `RedAgent` can now dispose any carried waste color, but **cross-color pickup is constrained**:
  - red always handles `red` waste,
  - red handles `yellow` only when exactly **one yellow waste remains** in the whole system,
  - red handles `green` only when exactly **one green waste remains** in the whole system.
- This prevents interference with normal transformation flow while solving final singleton leftovers.

### 4) Correct waste lifecycle in inventory
- Introduced `InventoryWaste` (lightweight token) for carried items.
- On pickup, grid `Waste` agents are removed from the grid/model registry and replaced in inventory by tokens.
- On drop, a fresh grid `Waste` agent is created.
- This avoids visualization crashes caused by unplaced `Waste` Mesa agents in inventories.

### 5) Safer live plotting/data collection
- Added `SafeDataCollector` (thread-safe wrapper around Mesa `DataCollector`) with locking.
- Added a safe fallback in dataframe building that trims to the shortest synchronized length if needed.
- This resolves intermittent live-plot errors caused by transient length mismatches under Solara rendering.

### 6) Visualization robustness and diagnostics
- Stabilized agent portrayal fields to avoid backend indexing issues.
- Added robot-count metrics to the data collector:
  - `Green Robots`, `Yellow Robots`, `Red Robots`.
- Added robot-count chart (page 2) for quick verification that robots are not disappearing.

### 7) Live robot status table (UI)
- Added a live table component showing, for each robot:
  - id,
  - type,
  - position,
  - current inventory contents.
- The table is displayed on **page 0** and includes current `Step` and `Running` state.
- Component wiring was adjusted so it re-renders with simulation ticks.

### 8) Step 3 kickoff: centralized orchestrator
- Added a model-level **MissionOrchestrator** that computes short-horizon assignments for all robot types.
- At each simulation step, the orchestrator allocates waste targets to reduce duplicate chasing:
  - `GreenAgent` gets prioritized `green` targets,
  - `YellowAgent` gets prioritized `yellow` targets,
  - `RedAgent` gets prioritized `red` targets, with singleton fallback to `yellow`/`green`.
- Robots still preserve their local deliberation logic; orchestrator targets act as guidance and are combined with local percepts, memory, and message-board updates.

### 9) Orchestrator diagnostics (Step 3 monitoring)
- Added orchestrator telemetry to the data collector:
  - `Orchestrator Assigned`
  - `Orchestrator Eligible`
  - `Orchestrator Coverage %`
  - `Assigned Green Targets`, `Assigned Yellow Targets`, `Assigned Red Targets`
- Added page 2 charts to monitor assignment quality over time.

### 10) Uncertainty-aware orchestrator scoring
- Replaced nearest-only assignment with a weighted target score.
- Current scoring combines:
  - Manhattan distance,
  - radioactivity penalty,
  - local crowding/contention penalty,
  - eastward flow bonus for handoff efficiency,
  - scarcity bonus when a waste color becomes rare.

## Behavior rules summary

| Robot type | Normal role | Extra coordination rule |
|---|---|---|
| `GreenAgent` | Collect green; transform `2 green → 1 yellow`; handoff east | If stuck with one green and no known second green, go to green rendezvous and drop for consolidation |
| `YellowAgent` | Collect yellow; transform `2 yellow → 1 red`; handoff east | If stuck with one yellow and no known second yellow, go to yellow rendezvous and drop for consolidation |
| `RedAgent` | Collect red and dispose at disposal zone | Can collect yellow/green **only** when exactly one of that color remains in whole system |

Additional deterministic coordination:
- At rendezvous cells, same-type pickup priority is given to the robot with the lowest `unique_id`.
- A short cooldown prevents immediate re-pick after deliberate drops.

## Conceptual choices

### 1. Discrete grid world
A discrete grid was chosen because the assignment is explicitly spatial and local perception is central. This aligns well with the agent-based modeling methodology presented in class.

### 2. Passive object agents
Radioactivity, waste, and disposal are implemented as agents without behavior. This keeps the environment explicit and easy to visualize.

### 3. Knowledge-based agents instead of random walkers
A first random strategy would satisfy a minimal version of Step 1, but it would be inefficient. This implementation adds memory (`visited`, `known_wastes`, `zone_map`, `target`) so the agents can progressively build a useful internal representation.

### 4. Greedy navigation with local constraints
Robots move toward known targets using a simple Manhattan-distance heuristic. This is less complex than full path planning and remains appropriate for the assignment scale.

### 5. Environment-side action validation
The `do()` method in `model.py` is responsible for validating and applying actions. That way it separates **agent intention** from **environment state transition**.

### 6. Observable progress through metrics
The model collects time-series data for:
- remaining green waste,
- remaining yellow waste,
- remaining red waste,
- disposed waste count,
- number of active messages.

These quantities are useful both for debugging and for evaluating collaboration efficiency.

## Progress achieved

### Step 1 — Implemented
The following core elements are implemented:
- grid environment,
- three radioactivity zones,
- three robot types,
- three waste types,
- waste disposal area,
- perception/deliberation/action loop,
- action execution in the environment,
- transformation rules,
- visualization and charting.

### Step 2 — Implemented
Communication capabilities are implemented through:
- shared message board,
- reading only new messages,
- message expiration,
- synchronization of known waste locations,
- broadcasting of discovered disposal location.

### Step 3 — Implemented
Step 3 is implemented with a centralized orchestrator and two assignment variants:
- `step3_orchestrator_nearest` (nearest-only),
- `step3_orchestrator_uncertainty` (uncertainty-aware weighted score).

Current follow-up work:
- extend significance reporting to additional pairwise comparisons.

## Uncertainty-weight calibration (short report)

### Search space
- `radio_penalty_weight`: `[1.0, 4.0]`
- `crowd_penalty_weight`: `[0.5, 2.5]`
- `east_bonus_weight_regular`: `[0.2, 1.0]`
- `east_bonus_weight_red`: `[0.1, 0.7]`
- `scarcity_le2_bonus`: `[0.2, 1.6]`
- `scarcity_eq1_bonus`: `[0.6, 2.2]`
- constraint: `scarcity_eq1_bonus >= scarcity_le2_bonus`

### Objective formula
The calibration minimizes:

`objective = (1 - completion_rate) * 1000 + remaining_mean * 25 + steps_mean + messages_mean / 1000`

Priority order is: completion > leftovers > speed > communication cost.

### Selected weights
Best candidate from `uncertainty_weight_calibration.csv`:
- `radio_penalty_weight = 2.967`
- `crowd_penalty_weight = 1.695`
- `east_bonus_weight_regular = 0.567`
- `east_bonus_weight_red = 0.414`
- `scarcity_le2_bonus = 0.885`
- `scarcity_eq1_bonus = 2.074`

These weights are now injected as the default uncertainty-scoring weights in the orchestrator.

### Final impact summary
- Step 3 remains the most robust family (100% completion across all 4 configs).
- Calibrated uncertainty-aware scoring is better in C1 and C4.
- Nearest-only remains faster in C2 and C3.

## Step impact experiment results (multi-seed)

The script below was executed with:
- `--seeds 20`
- `--base-seed 100`
- `--max-steps 500`

For the uncertainty-aware Step 3 mode, calibrated weights were applied:
- `--radio-weight 2.967`
- `--crowd-weight 1.695`
- `--east-regular-weight 0.567`
- `--east-red-weight 0.414`
- `--scarcity-le2-bonus 0.885`
- `--scarcity-eq1-bonus 2.074`

For each configuration, the table compares Step 1, Step 2, and Step 3 on:
- completion rate,
- average number of executed steps (`mean ± std`),
- average remaining waste,
- average messages sent.

For Step 3, an ablation is included:
- `step3_orchestrator_nearest` (nearest-only assignment),
- `step3_orchestrator_uncertainty` (uncertainty-aware weighted score).

### Configuration C1 — `C1_balanced_small` (`n_green=3`, `n_yellow=2`, `n_red=2`, `n_wastes=15`)

| Mode | Completion rate | Steps (mean ± std) | Remaining (mean ± std) | Messages (mean ± std) |
|---|---:|---:|---:|---:|
| Step 1 (no communication) | 100.0% | 183.10 ± 59.10 | 0.00 ± 0.00 | 0.00 ± 0.00 |
| Step 2 (communication) | 95.0% | 117.40 ± 91.20 | 0.25 ± 1.12 | 93.15 ± 55.56 |
| Step 3 (orchestrator nearest-only) | 100.0% | 88.05 ± 8.73 | 0.00 ± 0.00 | 84.80 ± 8.38 |
| Step 3 (orchestrator uncertainty-aware) | 100.0% | 86.30 ± 9.07 | 0.00 ± 0.00 | 83.40 ± 8.82 |

### Configuration C2 — `C2_green_heavy` (`n_green=5`, `n_yellow=2`, `n_red=2`, `n_wastes=25`)

| Mode | Completion rate | Steps (mean ± std) | Remaining (mean ± std) | Messages (mean ± std) |
|---|---:|---:|---:|---:|
| Step 1 (no communication) | 100.0% | 240.65 ± 69.00 | 0.00 ± 0.00 | 0.00 ± 0.00 |
| Step 2 (communication) | 100.0% | 111.85 ± 22.23 | 0.00 ± 0.00 | 119.65 ± 16.87 |
| Step 3 (orchestrator nearest-only) | 100.0% | 106.05 ± 14.47 | 0.00 ± 0.00 | 123.00 ± 12.00 |
| Step 3 (orchestrator uncertainty-aware) | 100.0% | 110.60 ± 24.90 | 0.00 ± 0.00 | 126.00 ± 19.03 |

### Configuration C3 — `C3_pipeline_strong` (`n_green=4`, `n_yellow=3`, `n_red=3`, `n_wastes=25`)

| Mode | Completion rate | Steps (mean ± std) | Remaining (mean ± std) | Messages (mean ± std) |
|---|---:|---:|---:|---:|
| Step 1 (no communication) | 100.0% | 158.20 ± 57.84 | 0.00 ± 0.00 | 0.00 ± 0.00 |
| Step 2 (communication) | 100.0% | 95.80 ± 18.06 | 0.00 ± 0.00 | 111.35 ± 16.34 |
| Step 3 (orchestrator nearest-only) | 100.0% | 84.90 ± 10.91 | 0.00 ± 0.00 | 106.15 ± 8.73 |
| Step 3 (orchestrator uncertainty-aware) | 100.0% | 91.00 ± 19.12 | 0.00 ± 0.00 | 111.15 ± 10.59 |

### Configuration C4 — `C4_red_limited` (`n_green=4`, `n_yellow=2`, `n_red=1`, `n_wastes=20`)

| Mode | Completion rate | Steps (mean ± std) | Remaining (mean ± std) | Messages (mean ± std) |
|---|---:|---:|---:|---:|
| Step 1 (no communication) | 85.0% | 311.65 ± 129.16 | 0.20 ± 0.52 | 0.00 ± 0.00 |
| Step 2 (communication) | 80.0% | 244.80 ± 157.81 | 0.50 ± 1.10 | 186.30 ± 145.24 |
| Step 3 (orchestrator nearest-only) | 100.0% | 121.45 ± 39.70 | 0.00 ± 0.00 | 73.75 ± 6.29 |
| Step 3 (orchestrator uncertainty-aware) | 100.0% | 113.35 ± 27.28 | 0.00 ± 0.00 | 74.45 ± 6.64 |

### Interpretation

Across these refreshed 20-seed experiments, Step 3 (both variants) is the most robust family:
- both Step 3 variants reach **100% completion** in all four configurations,
- both are consistently faster than Step 1 and usually faster than Step 2,
- both keep **remaining waste at 0.00** on average in all four configurations.

Specific impact of calibrated uncertainty-aware scoring (`uncertainty` vs `nearest`):
- **C1**: uncertainty-aware is faster and sends fewer messages.
- **C2/C3**: nearest-only is faster and sends fewer messages.
- **C4**: uncertainty-aware is faster, with similar message volume.

So, calibration improved uncertainty-aware behavior in C1 and C4, but nearest-only is still stronger in C2 and C3.

## Reproducing benchmark tables (canonical commands)

Use Python 3.11 or 3.12 when possible.

### Windows (PowerShell)
```powershell
cd C:\Users\hp\Desktop\Multi_Agent_System_Project
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cd robot_mission_MAS2026
python run_step_impact_experiments.py --seeds 20 --base-seed 100 --max-steps 500
```

Generated files:
- `robot_mission_MAS2026/step_impact_results.csv`
- `robot_mission_MAS2026/step_impact_summary.csv`

Calibrated weights search output:
- `robot_mission_MAS2026/uncertainty_weight_calibration.csv`

## Requirements

### Python version
Recommended:
- **Python 3.10+**

### Python packages
Install from pinned requirements:

```bash
python -m pip install -r requirements.txt
```

Installation steps are provided in **Quick start** above.

## How to run the project

```bash
cd robot_mission_MAS2026
solara run server.py
```

The interface includes:
- the grid visualization,
- sliders for the number of green, yellow, and red robots,
- a slider for the number of initial green wastes,
- live robot status table (id, type, position, inventory),
- plots for green/yellow/red waste counts,
- a plot for disposed waste,
- a plot for number of messages,
- orchestrator assignment/coverage diagnostics.

### UI pages map
- **Page 0**: grid + live robot status table.
- **Page 1**: waste and disposal plots.
- **Page 2**: communication and robot-count diagnostics.
- **Page 2** also includes orchestrator diagnostics:
  - assigned vs eligible robots,
  - assignment split by robot type,
  - assignment coverage percentage.

## Troubleshooting

- **Table/plots not updating**
  - Restart Solara server after code changes.
  - Confirm simulation is still running (`Running: True` in the live table).
- **`ModuleNotFoundError: mesa`**
  - Activate the project virtual environment and reinstall dependencies.
- **Solara/Mesa rendering crashes**
  - Ensure you use the pinned Mesa version (`3.3.0`) and restart the app.
- **Different behavior between runs**
  - Interactive server run is stochastic unless a fixed seed is set.

Communication should improve coordination by:
- reducing redundant searches,
- helping robots update stale targets,
- accelerating disposal after the disposal zone has been found.

## Current limitations

- Benchmarking is currently limited to internal multi-seed experiments (no external baseline yet).
- Navigation is greedy and local, not globally optimal.
- No collision handling or advanced resource contention policy is modeled.
- Statistical tests are included, but only for selected pairwise mode comparisons.
- Orchestrator uncertainty weights are functional but not fully calibrated across all configurations.

## Known caveats

- Interactive UI and headless execution may produce different trajectories if seeds differ.
- Greedy movement is intentionally simple and not globally optimal.


## Reproducibility note

The headless script uses `seed=42`, which is useful for reproducible runs. The visualization script does not explicitly set a seed in the default model instance, so successive interactive runs may differ.
