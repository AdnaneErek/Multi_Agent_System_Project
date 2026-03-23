# ============================================================
# Group: 27 | Date: 2026-03-16 | Members: Mounia, Adnane, Daniel
# server.py — Mesa 3.3.0 visualization with SolaraViz + SpaceRenderer
# ============================================================

from mesa.visualization import SolaraViz, SpaceRenderer, make_plot_component
import solara
from model import RobotMission
from agents import GreenAgent, YellowAgent, RedAgent, RobotAgent
from objects import Radioactivity, Waste, WasteDisposal


def agent_portrayal(agent):
    """Return portrayal dict for SpaceRenderer."""

    # Robots — big colored circles
    if isinstance(agent, RedAgent):
        return {
            "color": "#d62728",
            "size": 85,
            "marker": "o",
            "zorder": 10,
        }
    if isinstance(agent, YellowAgent):
        return {
            "color": "#ffbf00",
            "size": 95,
            "marker": "^",
            "zorder": 11,
        }
    if isinstance(agent, GreenAgent):
        return {
            "color": "#2ca02c",
            "size": 85,
            "marker": "o",
            "zorder": 9,
        }

    # Wastes — small colored squares
    if isinstance(agent, Waste):
        color_map = {"green": "#00cc00", "yellow": "#cccc00", "red": "#cc0000"}
        return {
            "color": color_map.get(agent.color, "gray"),
            "size": 25,
            "marker": "s",
            "zorder": 1,
        }

    # Waste disposal — dark square
    if isinstance(agent, WasteDisposal):
        return {"color": "#333333", "size": 80, "marker": "s", "zorder": 0}

    # Radioactivity — zone background colors
    if isinstance(agent, Radioactivity):
        zone_colors = {1: "#c8e6c9", 2: "#fff9c4", 3: "#ffcdd2"}
        return {
            "color": zone_colors.get(agent.zone, "#ffffff"),
            "size": 200,
            "marker": "s",
            "zorder": -1,
        }

    return {}


@solara.component
def robot_status_table(model, tick=0):
    """Live table with robot id, position and carried wastes."""

    robots = sorted(
        [a for a in model.agents if isinstance(a, RobotAgent)],
        key=lambda a: a.unique_id,
    )

    def robot_type(robot):
        if isinstance(robot, RedAgent):
            return "Red"
        if isinstance(robot, YellowAgent):
            return "Yellow"
        if isinstance(robot, GreenAgent):
            return "Green"
        return "Robot"

    lines = [
        "| ID | Type | Position | Holding |",
        "|---:|---|---|---|",
    ]

    for robot in robots:
        pos_text = str(robot.pos) if robot.pos is not None else "-"
        holding = [getattr(w, "color", "?") for w in robot.inventory]
        holding_text = ", ".join(holding) if holding else "-"
        lines.append(
            f"| {robot.unique_id} | {robot_type(robot)} | {pos_text} | {holding_text} |"
        )

    with solara.Card("Robot live status"):
        step_value = getattr(model, "steps", 0)
        running_value = getattr(model, "running", True)
        solara.Markdown(f"**Step:** {step_value}  |  **Running:** {running_value}")
        solara.Markdown("\n".join(lines))


model_params = {
    "width": 15,
    "height": 10,
    "n_green": {
        "type": "SliderInt",
        "value": 4,
        "label": "Green robots",
        "min": 1,
        "max": 10,
        "step": 1,
    },
    "n_yellow": {
        "type": "SliderInt",
        "value": 2,
        "label": "Yellow robots",
        "min": 1,
        "max": 10,
        "step": 1,
    },
    "n_red": {
        "type": "SliderInt",
        "value": 2,
        "label": "Red robots",
        "min": 1,
        "max": 10,
        "step": 1,
    },
    "n_wastes": {
        "type": "SliderInt",
        "value": 20,
        "label": "Initial green wastes",
        "min": 5,
        "max": 50,
        "step": 1,
    },
}

# Create model instance
model = RobotMission(width=15, height=10, n_green=4, n_yellow=2, n_red=2, n_wastes=20)

# Create SpaceRenderer for Mesa 3.3.0
renderer = SpaceRenderer(model=model, backend="matplotlib").render(
    agent_portrayal=agent_portrayal
)

page = SolaraViz(
    model,
    renderer,
    components=[
        make_plot_component(["Green Wastes", "Yellow Wastes", "Red Wastes"], page=1),
        make_plot_component(["Disposed"], page=1),
        (lambda m: robot_status_table(m, m.steps), 0),
        make_plot_component(["Green Robots", "Yellow Robots", "Red Robots"], page=2),
        make_plot_component(["Messages"], page=2),
    ],
    model_params=model_params,
    name="Robot Waste Cleanup Mission",
)

if __name__ == "__main__":
    page  # noqa