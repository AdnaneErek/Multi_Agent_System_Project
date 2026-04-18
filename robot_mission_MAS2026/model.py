# ============================================================
# Group: 27 | Date: 2026-03-16 | Members: Mounia, Adnane, Daniel
# model.py — RobotMission with communication (Mesa 3.3.0)
#
# Communication: shared message board in the environment.
# Agents post messages via model.broadcast() and read via
# model.get_messages(). Messages have a TTL and expire.
# ============================================================

import mesa
import pandas as pd
from threading import Lock
from objects import Radioactivity, Waste, WasteDisposal, InventoryWaste
from agents import (
    GreenAgent, YellowAgent, RedAgent, RobotAgent,
    ACTION_MOVE, ACTION_PICK, ACTION_TRANSFORM, ACTION_PUT,
)

# Message types
MSG_WASTE_DROPPED = "waste_dropped"     # "I dropped waste of color X at pos"
MSG_WASTE_PICKED = "waste_picked"       # "I picked up waste at pos (it's gone)"
MSG_DISPOSAL_FOUND = "disposal_found"   # "Waste disposal is at pos"


def count_green(model):
    return sum(
        1 for a in model.agents
        if isinstance(a, Waste) and a.color == "green" and a.pos is not None
    )

def count_yellow(model):
    return sum(
        1 for a in model.agents
        if isinstance(a, Waste) and a.color == "yellow" and a.pos is not None
    )

def count_red(model):
    return sum(
        1 for a in model.agents
        if isinstance(a, Waste) and a.color == "red" and a.pos is not None
    )

def count_disposed(model):
    return model.disposed_count

def count_messages(model):
    return len(model.message_board)


def count_total_messages(model):
    return model.total_messages_sent


def count_green_robots(model):
    return sum(1 for a in model.agents if isinstance(a, GreenAgent) and not isinstance(a, YellowAgent))


def count_yellow_robots(model):
    return sum(1 for a in model.agents if isinstance(a, YellowAgent) and not isinstance(a, RedAgent))


def count_red_robots(model):
    return sum(1 for a in model.agents if isinstance(a, RedAgent))


def count_orchestrator_assigned(model):
    if not model.use_orchestrator:
        return 0
    return model.orchestrator.last_stats.get("assigned_total", 0)


def count_orchestrator_eligible(model):
    if not model.use_orchestrator:
        return 0
    return model.orchestrator.last_stats.get("eligible_total", 0)


def count_orchestrator_coverage(model):
    if not model.use_orchestrator:
        return 0.0
    return model.orchestrator.last_stats.get("coverage_pct", 0.0)


def count_orchestrator_assigned_green(model):
    if not model.use_orchestrator:
        return 0
    return model.orchestrator.last_stats.get("assigned_green", 0)


def count_orchestrator_assigned_yellow(model):
    if not model.use_orchestrator:
        return 0
    return model.orchestrator.last_stats.get("assigned_yellow", 0)


def count_orchestrator_assigned_red(model):
    if not model.use_orchestrator:
        return 0
    return model.orchestrator.last_stats.get("assigned_red", 0)


class SafeDataCollector(mesa.DataCollector):
    """Thread-safe DataCollector for Solara live rendering.

    Solara plots can read model variables while the model is collecting,
    which may expose transient unequal list lengths and crash pandas.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = Lock()

    def collect(self, model):
        with self._lock:
            return super().collect(model)

    def get_model_vars_dataframe(self):
        with self._lock:
            if not self.model_vars:
                return pd.DataFrame()

            lengths = [len(v) for v in self.model_vars.values()]
            if len(set(lengths)) == 1:
                return pd.DataFrame(self.model_vars)

            min_len = min(lengths)
            safe_vars = {k: v[:min_len] for k, v in self.model_vars.items()}
            return pd.DataFrame(safe_vars)


class MissionOrchestrator:
    """Centralized coordinator with uncertainty-aware target assignment."""

    def __init__(self, model):
        self.model = model
        self.assignments = {}
        self.last_stats = {
            "eligible_green": 0,
            "eligible_yellow": 0,
            "eligible_red": 0,
            "eligible_total": 0,
            "assigned_green": 0,
            "assigned_yellow": 0,
            "assigned_red": 0,
            "assigned_total": 0,
            "coverage_pct": 0.0,
        }

    @staticmethod
    def _manhattan(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _radioactivity_level_at(self, pos):
        contents = self.model.grid.get_cell_list_contents([pos])
        for obj in contents:
            if isinstance(obj, Radioactivity):
                return float(obj.level)
        return 0.0

    def _on_grid_waste_positions(self):
        positions = {"green": [], "yellow": [], "red": []}
        for a in self.model.agents:
            if isinstance(a, Waste) and a.pos is not None and a.color in positions:
                positions[a.color].append(a.pos)
        return positions

    @staticmethod
    def _count_inventory(robot, color):
        return sum(1 for w in robot.inventory if getattr(w, "color", None) == color)

    @staticmethod
    def _is_carrying_any_waste(robot):
        return any(getattr(w, "color", None) in {"green", "yellow", "red"} for w in robot.inventory)

    def _crowding_near(self, pos, radius=1):
        crowd = 0
        for a in self.model.agents:
            if isinstance(a, RobotAgent) and a.pos is not None:
                if self._manhattan(a.pos, pos) <= radius:
                    crowd += 1
        return crowd

    def _score_target(self, robot, target_pos, target_color, remaining):
        """Lower score is better.

        Components:
        - distance cost,
        - radioactivity uncertainty penalty,
        - local crowding/contention penalty,
        - flow bonus toward east (helps handoff pipeline),
        - scarcity bonus for critical leftovers.
        """
        distance = self._manhattan(robot.pos, target_pos)
        radio_level = self._radioactivity_level_at(target_pos)
        crowding = self._crowding_near(target_pos, radius=1)
        weights = self.model.orchestrator_weights

        # uncertainty terms
        radio_penalty = weights["radio_penalty_weight"] * radio_level
        crowd_penalty = weights["crowd_penalty_weight"] * max(0, crowding - 1)

        # east-flow bonus for smoother handoff toward disposal column
        width_denom = max(1, self.model.grid.width - 1)
        east_progress = target_pos[0] / width_denom
        if isinstance(robot, RedAgent):
            east_bonus = weights["east_bonus_weight_red"] * east_progress
        else:
            east_bonus = weights["east_bonus_weight_regular"] * east_progress

        # prioritize scarce colors to reduce end-game deadlocks
        scarcity_bonus = 0.0
        if remaining.get(target_color, 0) <= 2:
            scarcity_bonus = weights["scarcity_le2_bonus"]
        if remaining.get(target_color, 0) == 1:
            scarcity_bonus = weights["scarcity_eq1_bonus"]

        return distance + radio_penalty + crowd_penalty - east_bonus - scarcity_bonus

    def _best_unreserved_target(self, robot, candidates, reserved, remaining):
        """Pick best target by uncertainty-aware score.

        candidates: iterable of (pos, color)
        """
        if not self.model.use_uncertainty_scoring:
            nearest = []
            for pos, color in candidates:
                if pos in reserved:
                    continue
                nearest.append((self._manhattan(robot.pos, pos), pos, color))

            if not nearest:
                return None, None

            nearest.sort(key=lambda t: (t[0], t[1][0], t[1][1]))
            _, best_pos, best_color = nearest[0]
            return best_pos, best_color

        ranked = []
        for pos, color in candidates:
            if pos in reserved:
                continue
            score = self._score_target(robot, pos, color, remaining)
            ranked.append((score, self._manhattan(robot.pos, pos), pos, color))

        if not ranked:
            return None, None

        ranked.sort(key=lambda t: (t[0], t[1], t[2][0], t[2][1]))
        _, _, best_pos, best_color = ranked[0]
        return best_pos, best_color

    def recompute(self):
        assignments = {}
        reserved = set()
        positions = self._on_grid_waste_positions()
        remaining = self.model.remaining_waste_counts()
        stats = {
            "eligible_green": 0,
            "eligible_yellow": 0,
            "eligible_red": 0,
            "eligible_total": 0,
            "assigned_green": 0,
            "assigned_yellow": 0,
            "assigned_red": 0,
            "assigned_total": 0,
            "coverage_pct": 0.0,
        }

        robots = [a for a in self.model.agents if isinstance(a, RobotAgent) and a.pos is not None]

        green_robots = [
            r for r in robots
            if isinstance(r, GreenAgent) and not isinstance(r, YellowAgent)
        ]
        yellow_robots = [
            r for r in robots
            if isinstance(r, YellowAgent) and not isinstance(r, RedAgent)
        ]
        red_robots = [r for r in robots if isinstance(r, RedAgent)]

        for robot in green_robots:
            if self._count_inventory(robot, "yellow") > 0:
                continue
            if self._count_inventory(robot, "green") >= 2:
                continue
            stats["eligible_green"] += 1
            green_candidates = [(p, "green") for p in positions["green"]]
            target, _ = self._best_unreserved_target(robot, green_candidates, reserved, remaining)
            if target is not None:
                assignments[robot.unique_id] = target
                reserved.add(target)
                stats["assigned_green"] += 1

        for robot in yellow_robots:
            if self._count_inventory(robot, "red") > 0:
                continue
            if self._count_inventory(robot, "yellow") >= 2:
                continue
            stats["eligible_yellow"] += 1
            yellow_candidates = [(p, "yellow") for p in positions["yellow"]]
            target, _ = self._best_unreserved_target(robot, yellow_candidates, reserved, remaining)
            if target is not None:
                assignments[robot.unique_id] = target
                reserved.add(target)
                stats["assigned_yellow"] += 1

        for robot in red_robots:
            if self._is_carrying_any_waste(robot):
                continue

            stats["eligible_red"] += 1

            collectable = {"red"}
            if remaining.get("yellow", 0) == 1:
                collectable.add("yellow")
            if remaining.get("green", 0) == 1:
                collectable.add("green")

            candidates = []
            for color in collectable:
                candidates.extend((p, color) for p in positions[color])

            target, _ = self._best_unreserved_target(robot, candidates, reserved, remaining)
            if target is not None:
                assignments[robot.unique_id] = target
                reserved.add(target)
                stats["assigned_red"] += 1

        stats["eligible_total"] = (
            stats["eligible_green"] + stats["eligible_yellow"] + stats["eligible_red"]
        )
        stats["assigned_total"] = (
            stats["assigned_green"] + stats["assigned_yellow"] + stats["assigned_red"]
        )
        if stats["eligible_total"] > 0:
            stats["coverage_pct"] = 100.0 * stats["assigned_total"] / stats["eligible_total"]

        self.assignments = assignments
        self.last_stats = stats

    def get_target(self, robot):
        return self.assignments.get(robot.unique_id)


class RobotMission(mesa.Model):
    """Mesa 3.3.0 model with inter-agent communication."""

    def __init__(self, width=15, height=10, n_green=4, n_yellow=2,
                 n_red=2, n_wastes=20, seed=None,
                 use_communication=True, use_orchestrator=True,
                 use_uncertainty_scoring=True,
                 orchestrator_weights=None):
        super().__init__(seed=seed)

        self.grid = mesa.space.MultiGrid(width, height, torus=False)
        self.disposed_count = 0
        self.use_communication = use_communication
        self.use_orchestrator = use_orchestrator
        self.use_uncertainty_scoring = use_uncertainty_scoring
        self.total_messages_sent = 0
        self.orchestrator_weights = {
            "radio_penalty_weight": 2.5,
            "crowd_penalty_weight": 1.5,
            "east_bonus_weight_regular": 0.60,
            "east_bonus_weight_red": 0.30,
            "scarcity_le2_bonus": 0.75,
            "scarcity_eq1_bonus": 1.25,
        }
        if orchestrator_weights:
            self.orchestrator_weights.update(orchestrator_weights)

        # ---- communication: shared message board ----
        self.message_board = []  # list of message dicts
        self.message_ttl = 50   # messages expire after 50 steps
        self.orchestrator = MissionOrchestrator(self)

        # zone boundaries
        self.zone1_end = width // 3
        self.zone2_end = 2 * width // 3

        # --- radioactivity on every cell ---
        for x in range(width):
            for y in range(height):
                zone = self._zone_of(x)
                rad = Radioactivity(self, zone)
                self.grid.place_agent(rad, (x, y))

        # --- waste disposal (random cell on last column) ---
        wd_y = self.random.randint(0, height - 1)
        self.waste_disposal_pos = (width - 1, wd_y)
        wd = WasteDisposal(self)
        self.grid.place_agent(wd, self.waste_disposal_pos)

        # --- initial green wastes in zone 1 ---
        for _ in range(n_wastes):
            x = self.random.randint(0, self.zone1_end - 1)
            y = self.random.randint(0, height - 1)
            w = Waste(self, "green")
            self.grid.place_agent(w, (x, y))

        # --- robot agents ---
        for _ in range(n_green):
            a = GreenAgent(self)
            x = self.random.randint(0, self.zone1_end - 1)
            y = self.random.randint(0, height - 1)
            self.grid.place_agent(a, (x, y))

        for _ in range(n_yellow):
            a = YellowAgent(self)
            x = self.random.randint(self.zone1_end, self.zone2_end - 1)
            y = self.random.randint(0, height - 1)
            self.grid.place_agent(a, (x, y))

        for _ in range(n_red):
            a = RedAgent(self)
            x = self.random.randint(self.zone2_end, width - 1)
            y = self.random.randint(0, height - 1)
            self.grid.place_agent(a, (x, y))

        # --- data collector ---
        self.datacollector = SafeDataCollector(
            model_reporters={
                "Green Wastes": count_green,
                "Yellow Wastes": count_yellow,
                "Red Wastes": count_red,
                "Disposed": count_disposed,
                "Messages": count_messages,
                "Total Messages Sent": count_total_messages,
                "Green Robots": count_green_robots,
                "Yellow Robots": count_yellow_robots,
                "Red Robots": count_red_robots,
                "Orchestrator Assigned": count_orchestrator_assigned,
                "Orchestrator Eligible": count_orchestrator_eligible,
                "Orchestrator Coverage %": count_orchestrator_coverage,
                "Assigned Green Targets": count_orchestrator_assigned_green,
                "Assigned Yellow Targets": count_orchestrator_assigned_yellow,
                "Assigned Red Targets": count_orchestrator_assigned_red,
            }
        )
        if self.use_orchestrator:
            self.orchestrator.recompute()
        self.datacollector.collect(self)

    # ===================== communication =====================

    def broadcast(self, sender, msg_type, pos, color=None):
        """Post a message to the shared board."""
        if not self.use_communication:
            return

        self.message_board.append({
            "type": msg_type,
            "sender_id": sender.unique_id,
            "pos": pos,
            "color": color,
            "step": self.steps,
        })
        self.total_messages_sent += 1

    def get_messages(self, since_step=0):
        """Return all messages posted since a given step."""
        if not self.use_communication:
            return []
        return [m for m in self.message_board if m["step"] >= since_step]

    def _expire_messages(self):
        """Remove messages older than TTL."""
        cutoff = self.steps - self.message_ttl
        self.message_board = [m for m in self.message_board if m["step"] >= cutoff]

    # ===================== helpers =====================

    def _zone_of(self, x):
        if x < self.zone1_end:
            return 1
        elif x < self.zone2_end:
            return 2
        else:
            return 3

    # ===================== percepts =====================

    def get_percepts(self, agent):
        x, y = agent.pos
        percepts = {}
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if abs(dx) + abs(dy) <= 1:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < self.grid.width and 0 <= ny < self.grid.height:
                        percepts[(nx, ny)] = list(
                            self.grid.get_cell_list_contents([(nx, ny)])
                        )
        return percepts

    # ===================== do =====================

    def do(self, agent, action):
        action_type = action[0] if isinstance(action, tuple) else action

        if action_type == ACTION_MOVE:
            target = action[1]
            if (
                0 <= target[0] < self.grid.width
                and 0 <= target[1] < self.grid.height
                and self._zone_of(target[0]) in agent.allowed_zones
            ):
                self.grid.move_agent(agent, target)

        elif action_type == ACTION_PICK:
            waste_obj = action[1]
            cell = self.grid.get_cell_list_contents([agent.pos])
            if waste_obj in cell:
                self.grid.remove_agent(waste_obj)
                # remove from model registry; inventory keeps lightweight token
                waste_obj.remove()
                agent.inventory.append(InventoryWaste(waste_obj.color))
                # COMMUNICATE: tell others this waste is gone
                self.broadcast(agent, MSG_WASTE_PICKED, agent.pos, waste_obj.color)

        elif action_type == ACTION_TRANSFORM:
            if isinstance(agent, GreenAgent) and not isinstance(agent, YellowAgent):
                greens = [w for w in agent.inventory if w.color == "green"]
                if len(greens) >= 2:
                    agent.inventory.remove(greens[0])
                    agent.inventory.remove(greens[1])
                    agent.inventory.append(InventoryWaste("yellow"))

            elif isinstance(agent, YellowAgent) and not isinstance(agent, RedAgent):
                yellows = [w for w in agent.inventory if w.color == "yellow"]
                if len(yellows) >= 2:
                    agent.inventory.remove(yellows[0])
                    agent.inventory.remove(yellows[1])
                    agent.inventory.append(InventoryWaste("red"))

        elif action_type == ACTION_PUT:
            waste_obj = action[1]
            if waste_obj in agent.inventory:
                agent.inventory.remove(waste_obj)
                if isinstance(agent, RedAgent) and self._is_disposal(agent.pos):
                    self.disposed_count += 1
                else:
                    dropped = Waste(self, waste_obj.color)
                    self.grid.place_agent(dropped, agent.pos)
                    # COMMUNICATE: tell others about dropped waste
                    self.broadcast(agent, MSG_WASTE_DROPPED, agent.pos, waste_obj.color)

        # If agent found waste disposal, share the location
        for obj in self.grid.get_cell_list_contents([agent.pos]):
            if isinstance(obj, WasteDisposal):
                self.broadcast(agent, MSG_DISPOSAL_FOUND, agent.pos)
                break

        return self.get_percepts(agent)

    def _is_disposal(self, pos):
        cell = self.grid.get_cell_list_contents([pos])
        return any(isinstance(o, WasteDisposal) for o in cell)

    def remaining_waste_counts(self):
        """Count remaining wastes by color (grid + robot inventories)."""
        counts = {"green": 0, "yellow": 0, "red": 0}

        # on-grid wastes
        for a in self.agents:
            if isinstance(a, Waste) and a.pos is not None:
                counts[a.color] += 1

        # carried wastes
        robots = [a for a in self.agents if isinstance(a, RobotAgent)]
        for robot in robots:
            for w in robot.inventory:
                color = getattr(w, "color", None)
                if color in counts:
                    counts[color] += 1

        return counts

    def get_orchestrator_target(self, agent):
        if not self.use_orchestrator:
            return None
        return self.orchestrator.get_target(agent)

    # ===================== step =====================

    def step(self):
        robots = [a for a in self.agents if isinstance(a, RobotAgent)]
        self.random.shuffle(robots)
        for robot in robots:
            if self.use_orchestrator:
                self.orchestrator.recompute()
            robot.step()
        if self.use_orchestrator:
            self.orchestrator.recompute()
        self._expire_messages()
        self.datacollector.collect(self)

        # stop when all waste is disposed
        waste_on_grid = sum(
            1 for a in self.agents if isinstance(a, Waste) and a.pos is not None
        )
        waste_carried = sum(len(r.inventory) for r in robots)
        if waste_on_grid + waste_carried == 0:
            self.running = False