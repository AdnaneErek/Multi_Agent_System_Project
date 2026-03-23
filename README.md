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

## Project structure

```text
.
├── agents.py     # Robot agents, knowledge base, deliberation, navigation, communication use
├── model.py      # RobotMission model, grid, action execution, message board, data collection
├── objects.py    # Passive environment objects: radioactivity, waste, disposal zone
├── server.py     # Mesa/Solara visualization
├── run.py        # Headless execution + result plots
└── README.md     # Project description and execution guide
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

### Step 3 — Not implemented
The assignment states that uncertainties are planned for Step 3 and are still to be defined. 

## Requirements

### Python version
Recommended:
- **Python 3.10+**

### Python packages
Install the following packages:

```text
mesa==3.3.0
matplotlib
solara
```

## Installation

Create and activate a virtual environment, then install the dependencies.

### On Windows (PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### On Linux / macOS
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## How to run the project

```bash
solara run server.py
```

The interface includes:
- the grid visualization,
- sliders for the number of green, yellow, and red robots,
- a slider for the number of initial green wastes,
- plots for green/yellow/red waste counts,
- a plot for disposed waste,
- a plot for number of messages.

Communication should improve coordination by:
- reducing redundant searches,
- helping robots update stale targets,
- accelerating disposal after the disposal zone has been found.

## Current limitations

- No formal benchmark is included to compare communication vs no communication.
- No uncertainty model is implemented.
- Navigation is greedy and local, not globally optimal.
- No collision handling or advanced resource contention policy is modeled.
- There is no experiment script to run many seeds and compute averages.


## Reproducibility note

The headless script uses `seed=42`, which is useful for reproducible runs. The visualization script does not explicitly set a seed in the default model instance, so successive interactive runs may differ.
