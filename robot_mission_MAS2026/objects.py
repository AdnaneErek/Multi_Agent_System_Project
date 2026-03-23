# ============================================================
# Group: 27 | Date: 2026-03-16 | Members: Mounia, Adnane, Daniel
# objects.py — Passive environment objects (Mesa 3.x agents, no behavior)
# ============================================================

import random
import mesa


class Radioactivity(mesa.Agent):
    """Passive agent on every cell. Encodes zone via its radioactivity level."""

    def __init__(self, model, zone):
        super().__init__(model)
        self.zone = zone
        if zone == 1:
            self.level = random.uniform(0.0, 0.33)
        elif zone == 2:
            self.level = random.uniform(0.33, 0.66)
        else:
            self.level = random.uniform(0.66, 1.0)


class Waste(mesa.Agent):
    """Represents a waste object on the grid."""

    def __init__(self, model, color):
        super().__init__(model)
        assert color in ("green", "yellow", "red")
        self.color = color


class InventoryWaste:
    """Lightweight token for carried waste (not a Mesa agent)."""

    def __init__(self, color):
        assert color in ("green", "yellow", "red")
        self.color = color


class WasteDisposal(mesa.Agent):
    """Marks the waste disposal zone (easternmost column)."""

    def __init__(self, model):
        super().__init__(model)