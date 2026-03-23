# ============================================================
# Group: XX | Date: 2026-03-16 | Members: Mounia, [partner]
# model.py — RobotMission with communication (Mesa 3.3.0)
#
# Communication: shared message board in the environment.
# Agents post messages via model.broadcast() and read via
# model.get_messages(). Messages have a TTL and expire.
# ============================================================

import mesa
from objects import Radioactivity, Waste, WasteDisposal
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


class RobotMission(mesa.Model):
    """Mesa 3.3.0 model with inter-agent communication."""

    def __init__(self, width=15, height=10, n_green=4, n_yellow=2,
                 n_red=2, n_wastes=20, seed=None):
        super().__init__(seed=seed)

        self.grid = mesa.space.MultiGrid(width, height, torus=False)
        self.disposed_count = 0

        # ---- communication: shared message board ----
        self.message_board = []  # list of message dicts
        self.message_ttl = 50   # messages expire after 50 steps

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
        self.datacollector = mesa.DataCollector(
            model_reporters={
                "Green Wastes": count_green,
                "Yellow Wastes": count_yellow,
                "Red Wastes": count_red,
                "Disposed": count_disposed,
                "Messages": count_messages,
            }
        )
        self.datacollector.collect(self)

    # ===================== communication =====================

    def broadcast(self, sender, msg_type, pos, color=None):
        """Post a message to the shared board."""
        self.message_board.append({
            "type": msg_type,
            "sender_id": sender.unique_id,
            "pos": pos,
            "color": color,
            "step": self.steps,
        })

    def get_messages(self, since_step=0):
        """Return all messages posted since a given step."""
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
                agent.inventory.append(waste_obj)
                # COMMUNICATE: tell others this waste is gone
                self.broadcast(agent, MSG_WASTE_PICKED, agent.pos, waste_obj.color)

        elif action_type == ACTION_TRANSFORM:
            if isinstance(agent, GreenAgent) and not isinstance(agent, YellowAgent):
                greens = [w for w in agent.inventory if w.color == "green"]
                if len(greens) >= 2:
                    agent.inventory.remove(greens[0])
                    agent.inventory.remove(greens[1])
                    greens[0].remove()
                    greens[1].remove()
                    agent.inventory.append(Waste(self, "yellow"))

            elif isinstance(agent, YellowAgent) and not isinstance(agent, RedAgent):
                yellows = [w for w in agent.inventory if w.color == "yellow"]
                if len(yellows) >= 2:
                    agent.inventory.remove(yellows[0])
                    agent.inventory.remove(yellows[1])
                    yellows[0].remove()
                    yellows[1].remove()
                    agent.inventory.append(Waste(self, "red"))

        elif action_type == ACTION_PUT:
            waste_obj = action[1]
            if waste_obj in agent.inventory:
                agent.inventory.remove(waste_obj)
                if isinstance(agent, RedAgent) and self._is_disposal(agent.pos):
                    self.disposed_count += 1
                    waste_obj.remove()
                else:
                    self.grid.place_agent(waste_obj, agent.pos)
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

    # ===================== step =====================

    def step(self):
        robots = [a for a in self.agents if isinstance(a, RobotAgent)]
        self.random.shuffle(robots)
        for robot in robots:
            robot.step()
        self._expire_messages()
        self.datacollector.collect(self)

        # stop when all waste is disposed
        waste_on_grid = sum(
            1 for a in self.agents if isinstance(a, Waste) and a.pos is not None
        )
        waste_carried = sum(len(r.inventory) for r in robots)
        if waste_on_grid + waste_carried == 0:
            self.running = False