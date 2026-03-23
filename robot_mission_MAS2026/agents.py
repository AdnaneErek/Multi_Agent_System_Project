# ============================================================
# Group: XX | Date: 2026-03-16 | Members: Mounia, [partner]
# agents.py — Robots with knowledge base + communication
#
# Step 2: Agents read messages from the shared board to learn
# about waste locations discovered by other robots, waste that
# has been picked up, and the waste disposal position.
# ============================================================

import random
import mesa
from objects import Waste, WasteDisposal, Radioactivity

# --------------- action constants ---------------
ACTION_MOVE = "move"
ACTION_PICK = "pick"
ACTION_TRANSFORM = "transform"
ACTION_PUT = "put"
ACTION_WAIT = "wait"

# --------------- message types (match model.py) ---------------
MSG_WASTE_DROPPED = "waste_dropped"
MSG_WASTE_PICKED = "waste_picked"
MSG_DISPOSAL_FOUND = "disposal_found"


# ================= helpers (operate on knowledge only) =================

def _zone_from_percepts(percepts, pos):
    for obj in percepts.get(pos, []):
        if isinstance(obj, Radioactivity):
            return obj.zone
    return 0


def _find_waste_in_cell(percepts, pos, color):
    for obj in percepts.get(pos, []):
        if isinstance(obj, Waste) and obj.color == color:
            return obj
    return None


def _has_waste_disposal(percepts, pos):
    for obj in percepts.get(pos, []):
        if isinstance(obj, WasteDisposal):
            return True
    return False


def _manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


# ================= Base Robot =================

class RobotAgent(mesa.Agent):
    allowed_zones = set()
    target_color = ""
    needed = 0

    def __init__(self, model):
        super().__init__(model)
        self.inventory = []
        self.knowledge = {
            # transient
            "pos": None,
            "zone": 0,
            "percepts": {},
            "inventory": self.inventory,
            "grid_width": model.grid.width,
            "grid_height": model.grid.height,
            # persistent memory
            "zone_map": {},
            "known_wastes": {},
            "visited": set(),
            "waste_disposal": None,
            "target": None,
            # communication tracking
            "last_msg_step": 0,  # last step at which we read messages
        }

    # ---------- Mesa step ----------
    def step(self):
        percepts = self.model.get_percepts(self)
        self._update_knowledge(percepts)
        self._read_messages()
        action = self.deliberate(self.knowledge)
        new_percepts = self.model.do(self, action)
        self._update_knowledge(new_percepts)

    def _update_knowledge(self, percepts):
        k = self.knowledge
        k["pos"] = self.pos
        k["zone"] = _zone_from_percepts(percepts, self.pos)
        k["percepts"] = percepts
        k["inventory"] = self.inventory
        k["visited"].add(self.pos)

        for p, contents in percepts.items():
            for obj in contents:
                if isinstance(obj, Radioactivity):
                    k["zone_map"][p] = obj.zone
                if isinstance(obj, WasteDisposal):
                    k["waste_disposal"] = p

            waste_colors = [o.color for o in contents if isinstance(o, Waste)]
            if waste_colors:
                k["known_wastes"][p] = waste_colors
            else:
                k["known_wastes"].pop(p, None)

    def _read_messages(self):
        """Read new messages from the shared board and update knowledge."""
        k = self.knowledge
        messages = self.model.get_messages(since_step=k["last_msg_step"])
        k["last_msg_step"] = self.model.steps

        for msg in messages:
            # skip own messages
            if msg["sender_id"] == self.unique_id:
                continue

            if msg["type"] == MSG_WASTE_DROPPED:
                # another robot dropped waste somewhere — remember it
                pos = msg["pos"]
                color = msg["color"]
                if pos in k["known_wastes"]:
                    if color not in k["known_wastes"][pos]:
                        k["known_wastes"][pos].append(color)
                else:
                    k["known_wastes"][pos] = [color]

            elif msg["type"] == MSG_WASTE_PICKED:
                # waste was picked up — remove from memory
                pos = msg["pos"]
                color = msg["color"]
                if pos in k["known_wastes"]:
                    while color in k["known_wastes"][pos]:
                        k["known_wastes"][pos].remove(color)
                    if not k["known_wastes"][pos]:
                        del k["known_wastes"][pos]
                # if our target was that position, clear it
                if k["target"] == pos:
                    k["target"] = None

            elif msg["type"] == MSG_DISPOSAL_FOUND:
                k["waste_disposal"] = msg["pos"]

    def deliberate(self, knowledge):
        raise NotImplementedError

    # ---------- navigation helpers ----------

    def _in_bounds(self, pos, k):
        return 0 <= pos[0] < k["grid_width"] and 0 <= pos[1] < k["grid_height"]

    def _zone_allowed(self, pos, k):
        cell = k["percepts"].get(pos, [])
        for obj in cell:
            if isinstance(obj, Radioactivity):
                return obj.zone in self.allowed_zones
        if pos in k["zone_map"]:
            return k["zone_map"][pos] in self.allowed_zones
        return True

    def _can_go(self, pos, k):
        return self._in_bounds(pos, k) and self._zone_allowed(pos, k)

    def _get_neighbors(self, pos, k):
        neighbors = []
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            np_ = (pos[0] + dx, pos[1] + dy)
            if self._can_go(np_, k):
                neighbors.append(np_)
        return neighbors

    def _random_neighbor(self, pos, k):
        neighbors = self._get_neighbors(pos, k)
        return random.choice(neighbors) if neighbors else pos

    def _explore_move(self, pos, k):
        neighbors = self._get_neighbors(pos, k)
        if not neighbors:
            return pos
        unvisited = [n for n in neighbors if n not in k["visited"]]
        if unvisited:
            return random.choice(unvisited)
        return random.choice(neighbors)

    def _nearest_known_waste(self, k):
        best, best_dist = None, float("inf")
        for p, colors in k["known_wastes"].items():
            if self.target_color in colors:
                d = _manhattan(p, k["pos"])
                if 0 < d < best_dist:
                    best_dist = d
                    best = p
        return best

    def _step_toward(self, pos, target, k):
        dx = target[0] - pos[0]
        dy = target[1] - pos[1]
        candidates = []
        if abs(dx) >= abs(dy):
            if dx > 0: candidates.append((pos[0] + 1, pos[1]))
            elif dx < 0: candidates.append((pos[0] - 1, pos[1]))
            if dy > 0: candidates.append((pos[0], pos[1] + 1))
            elif dy < 0: candidates.append((pos[0], pos[1] - 1))
        else:
            if dy > 0: candidates.append((pos[0], pos[1] + 1))
            elif dy < 0: candidates.append((pos[0], pos[1] - 1))
            if dx > 0: candidates.append((pos[0] + 1, pos[1]))
            elif dx < 0: candidates.append((pos[0] - 1, pos[1]))
        for c in candidates:
            if self._can_go(c, k):
                return c
        return self._random_neighbor(pos, k)

    def _navigate_to(self, pos, target, k):
        if pos == target:
            k["target"] = None
            return None
        return self._step_toward(pos, target, k)

    def _lock_target(self, k, target):
        k["target"] = target

    def _clear_target(self, k):
        k["target"] = None

    def _validate_target(self, k):
        """Clear target if waste is no longer there (from messages or observation)."""
        if k["target"]:
            if k["target"] not in k["known_wastes"] or \
               self.target_color not in k["known_wastes"].get(k["target"], []):
                self._clear_target(k)


# ================= Green Robot — zone 1 only =================

class GreenAgent(RobotAgent):
    allowed_zones = {1}
    target_color = "green"
    needed = 2

    def deliberate(self, k):
        pos = k["pos"]
        inv = k["inventory"]
        percepts = k["percepts"]

        # carrying yellow → deliver east
        yellows_carried = [w for w in inv if w.color == "yellow"]
        if yellows_carried:
            east = (pos[0] + 1, pos[1])
            if self._can_go(east, k):
                return (ACTION_MOVE, east)
            else:
                self._clear_target(k)
                return (ACTION_PUT, yellows_carried[0])

        # 2 greens → transform
        greens_carried = [w for w in inv if w.color == "green"]
        if len(greens_carried) >= self.needed:
            self._clear_target(k)
            return (ACTION_TRANSFORM,)

        # green waste here → pick
        waste_here = _find_waste_in_cell(percepts, pos, self.target_color)
        if waste_here and len(greens_carried) < self.needed:
            return (ACTION_PICK, waste_here)

        # navigate to known waste (from observation OR messages) or explore
        self._validate_target(k)
        if not k["target"]:
            nearest = self._nearest_known_waste(k)
            if nearest:
                self._lock_target(k, nearest)

        if k["target"]:
            next_pos = self._navigate_to(pos, k["target"], k)
            if next_pos:
                return (ACTION_MOVE, next_pos)

        return (ACTION_MOVE, self._explore_move(pos, k))


# ================= Yellow Robot — zones 1 & 2 =================

class YellowAgent(RobotAgent):
    allowed_zones = {1, 2}
    target_color = "yellow"
    needed = 2

    def deliberate(self, k):
        pos = k["pos"]
        inv = k["inventory"]
        percepts = k["percepts"]

        # carrying red → deliver east
        reds_carried = [w for w in inv if w.color == "red"]
        if reds_carried:
            east = (pos[0] + 1, pos[1])
            if self._can_go(east, k):
                return (ACTION_MOVE, east)
            else:
                self._clear_target(k)
                return (ACTION_PUT, reds_carried[0])

        # 2 yellows → transform
        yellows_carried = [w for w in inv if w.color == "yellow"]
        if len(yellows_carried) >= self.needed:
            self._clear_target(k)
            return (ACTION_TRANSFORM,)

        # yellow waste here → pick
        waste_here = _find_waste_in_cell(percepts, pos, self.target_color)
        if waste_here and len(yellows_carried) < self.needed:
            return (ACTION_PICK, waste_here)

        # navigate using messages + observation
        self._validate_target(k)
        if not k["target"]:
            nearest = self._nearest_known_waste(k)
            if nearest:
                self._lock_target(k, nearest)

        if k["target"]:
            next_pos = self._navigate_to(pos, k["target"], k)
            if next_pos:
                return (ACTION_MOVE, next_pos)

        return (ACTION_MOVE, self._explore_move(pos, k))


# ================= Red Robot — zones 1, 2 & 3 =================

class RedAgent(RobotAgent):
    allowed_zones = {1, 2, 3}
    target_color = "red"
    needed = 1

    def deliberate(self, k):
        pos = k["pos"]
        inv = k["inventory"]
        percepts = k["percepts"]

        # carrying red → head to disposal
        reds_carried = [w for w in inv if w.color == "red"]
        if reds_carried:
            if _has_waste_disposal(percepts, pos):
                self._clear_target(k)
                return (ACTION_PUT, reds_carried[0])

            # use remembered disposal location (from own observation or message)
            if k["waste_disposal"]:
                next_pos = self._step_toward(pos, k["waste_disposal"], k)
                return (ACTION_MOVE, next_pos)

            # unknown disposal — go east
            east = (pos[0] + 1, pos[1])
            if self._can_go(east, k):
                return (ACTION_MOVE, east)
            else:
                return (ACTION_MOVE, self._random_neighbor(pos, k))

        # red waste here → pick
        waste_here = _find_waste_in_cell(percepts, pos, self.target_color)
        if waste_here:
            return (ACTION_PICK, waste_here)

        # navigate using messages + observation
        self._validate_target(k)
        if not k["target"]:
            nearest = self._nearest_known_waste(k)
            if nearest:
                self._lock_target(k, nearest)

        if k["target"]:
            next_pos = self._navigate_to(pos, k["target"], k)
            if next_pos:
                return (ACTION_MOVE, next_pos)

        return (ACTION_MOVE, self._explore_move(pos, k))