from enum import Enum
from threading import RLock
from typing import Dict, List, Tuple, Any
import logging
from functools import wraps
import random

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
CW_API_LOCK = RLock()
_pocket = {'call_count': 0}

def _api(method):
    @wraps(method)
    def wrapper(*args, **kwargs):
        with CW_API_LOCK:
            _pocket['call_count'] += 1
            logger.debug(f"{_pocket['call_count']:7} Calling {method.__name__} with args: {args[1:]}, kwargs: {kwargs}")
            result = method(*args, **kwargs)
            logger.debug(f"{_pocket['call_count']:7} {method.__name__} returned: {result}")
        return result
    return wrapper

class Direction(Enum):
    LOCAL = (0, 0)
    NORTH = (0, 1)
    SOUTH = (0, -1)
    EAST = (1, 0)
    WEST = (-1, 0)
    NORTHEAST = (1, 1)
    NORTHWEST = (-1, 1)
    SOUTHEAST = (1, -1)
    SOUTHWEST = (-1, -1)

class ItemType(Enum):
    FOOD = "food"
    GOLD = "gold"
    ARTIFACT = "artifact"
    RESOURCE = "resource"
    TOOL = "tool"
    WEAPON = "weapon"

class Status(Enum):
    IDLE = "IDLE"
    EXEC_GOAL = "EXEC_GOAL"


class Item:
    def __init__(self, item_type: ItemType, name: str, value: int = 0):
        self.type = item_type
        self.name = name
        self.value = value

    def __repr__(self):
        return f"{self.name} ({self.type.value})"


class Cell:
    def __init__(self):
        self.obstacle: bool = False
        self.trap: bool = False
        self.pit: bool = False
        self.items: List[Item] = []
        self.agents: List['Agent'] = []

    @_api
    def is_passable(self) -> bool:
        return not self.obstacle and not self.pit

    def __repr__(self):
        features = []
        if self.obstacle: features.append("O")
        if self.pit: features.append("P")
        if self.trap: features.append("T")
        return f"Cell({', '.join(features)}, items={len(self.items)}, agents={len(self.agents)})"


class Agent:
    def __init__(self, name: str, health: int = 100, energy: int = 100, on_goal_set=None):
        self.name = name
        self.health = health
        self.energy = energy
        self.inventory: List[Item] = []
        self.atp: int = 0
        self.position: Tuple[int, int] = (0, 0)
        self.goal = None
        self.status = Status.IDLE
        self.on_goal_set = on_goal_set
        self.goal_log = []

    def take_goal_log(self):
        with CW_API_LOCK:
            logs = self.goal_log[:]
            self.goal_log.clear()
            return logs

    @_api
    def append_goal_log(self, message):
            self.goal_log.append(message)

    @_api
    def set_goal(self, goal: str):
        """Set a new goal for the agent."""
        self.goal = goal
        self.status = Status.EXEC_GOAL
        if self.on_goal_set:
            self.on_goal_set(self)

    @_api
    def set_idle(self):
        """It is expected that agent controller will call this after goal reached."""
        self.goal = None
        self.status = Status.IDLE

    @_api
    def can_act(self) -> bool:
        return self.atp > 0 and self.health > 0 and self.energy > 0

    def __repr__(self):
        return f"Agent({self.name}, ♥{self.health}, ⚡{self.energy}, ATP:{self.atp}, Status: {self.status})"

def _ensure_ortho_direction(direction: Direction):
    if direction not in [Direction.EAST, Direction.NORTH, Direction.SOUTH, Direction.WEST]:
        raise ValueError(f'Not ortho-direction: {direction}')

class CellWorld:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.grid = [[Cell() for _ in range(height)] for _ in range(width)]
        self.agents: Dict[str, Agent] = {}
        self.turn: int = 0

    @_api
    def new_turn(self, atp=100):
        """Advance to new turn and reset agent ATP"""
        self.turn += 1
        for agent in self.agents.values():
            agent.atp = atp

    @_api
    def add_agent(self, agent: Agent, position: Tuple[int, int]) -> bool:
        """Place agent in the world at specified position"""
        x, y = position
        if not self._is_valid_position(x, y):
            return False

        if agent.name in self.agents:
            return False

        self.agents[agent.name] = agent
        agent.position = position
        self.grid[x][y].agents.append(agent)
        return True

    @_api
    def remove_agent(self, agent):
        if agent.name not in self.agents:
            return False
        x, y = agent.position
        cell = self.grid[x][y]
        cell.agents.remove(agent)
        del self.agents[agent.name]
        return True

    @_api
    def move_agent(self, agent: Agent, direction: Direction) -> bool:
        """Attempt to move agent in specified direction"""
        _ensure_ortho_direction(direction)

        if not self._validate_agent(agent) or not agent.can_act():
            return False

        dx, dy = direction.value
        x, y = agent.position
        new_x, new_y = x + dx, y + dy

        if not self._is_valid_position(new_x, new_y):
            return False

        new_cell = self.grid[new_x][new_y]
        if not new_cell.is_passable():
            return False

        # Handle trap activation
        if new_cell.trap:
            agent.health -= 20
            new_cell.trap = False

        # Consume ATP and move
        agent.atp -= 10
        self.grid[x][y].agents.remove(agent)
        new_cell.agents.append(agent)
        agent.position = (new_x, new_y)
        # Handle target death
        if agent.health <= 0:
            self._handle_agent_death(agent)
        return True

    @_api
    def attack(self, attacker: Agent, direction: Direction) -> bool:
        """Perform attack in specified direction"""
        _ensure_ortho_direction(direction)

        if not self._validate_agent(attacker) or not attacker.can_act():
            return False

        dx, dy = direction.value
        x, y = attacker.position
        target_x, target_y = x + dx, y + dy

        if not self._is_valid_position(target_x, target_y):
            return False

        target_cell = self.grid[target_x][target_y]
        if not target_cell.agents:
            return False

        # Calculate damage
        base_damage = 10
        weapon = next((i for i in attacker.inventory if i.type == ItemType.WEAPON), None)
        damage = base_damage + (weapon.value if weapon else 0)

        # Apply damage
        target = random.choice(target_cell.agents)
        target.health -= damage

        # Handle target death
        if target.health <= 0:
            self._handle_agent_death(target)

        attacker.atp -= 20
        return True

    def _handle_agent_death(self, agent: Agent):
        """Handle agent death and inventory drop"""
        x, y = agent.position
        cell = self.grid[x][y]
        cell.items.extend(agent.inventory)
        agent.inventory.clear()
        self.remove_agent(agent)

    @_api
    def pick_item(self, agent: Agent, item_index: int) -> bool:
        """Pick up item from current cell"""
        if not self._validate_agent(agent) or not agent.can_act():
            return False

        cell = self.grid[agent.position[0]][agent.position[1]]
        if 0 <= item_index < len(cell.items):
            item = cell.items.pop(item_index)
            agent.inventory.append(item)
            agent.atp -= 5
            return True
        return False

    @_api
    def eat_food(self, agent: Agent) -> bool:
        """Consume food item to restore energy"""
        if not self._validate_agent(agent) or not agent.can_act():
            return False

        food = next((i for i in agent.inventory if i.type == ItemType.FOOD), None)
        if food:
            agent.energy = min(100, agent.energy + food.value)
            agent.inventory.remove(food)
            agent.atp -= 5
            return True
        return False

    @_api
    def inspect_vicinity(self, agent: Agent) -> Dict[Direction, Dict[str, Any]]:
        """Return information about adjacent cells"""
        result = {}
        x, y = agent.position

        for direction in Direction:
            dx, dy = direction.value
            nx, ny = x + dx, y + dy
            cell_info = {
                "agents": [],
                "items": [],
                "terrain": []
            }

            if self._is_valid_position(nx, ny):
                cell = self.grid[nx][ny]
                cell_info["agents"] = [a.name for a in cell.agents]
                cell_info["items"] = [item.name for item in cell.items]
                if cell.obstacle: cell_info["terrain"].append("obstacle")
                if cell.pit: cell_info["terrain"].append("pit")
                if cell.trap: cell_info["terrain"].append("trap")

            result[direction] = cell_info

        return result

    @_api
    def inspect_agent(self, agent):
        """Return detailed information about an agent"""
        if agent.name not in self.agents:
            return {"error": "Agent does not exist"}

        target_agent = self.agents[agent.name]
        return {
            "name": target_agent.name,
            "position": target_agent.position,
            "health": target_agent.health,
            "energy": target_agent.energy,
            "inventory": [item.name for item in target_agent.inventory],
            "atp": target_agent.atp
        }

    # World management methods

    @_api
    def add_item(self, x: int, y: int, item: Item) -> bool:
        if not self._is_valid_position(x, y):
            return False
        self.grid[x][y].items.append(item)
        return True

    @_api
    def add_obstacle(self, x: int, y: int) -> bool:
        if not self._is_valid_position(x, y):
            return False
        self.grid[x][y].obstacle = True
        return True

    @_api
    def add_trap(self, x: int, y: int) -> bool:
        if not self._is_valid_position(x, y):
            return False
        self.grid[x][y].trap = True
        return True

    @_api
    def add_pit(self, x: int, y: int) -> bool:
        if not self._is_valid_position(x, y):
            return False
        self.grid[x][y].pit = True
        return True

    # Validation helpers
    def _validate_agent(self, agent: Agent) -> bool:
        return agent is not None and self.agents.get(agent.name) is agent

    def _is_valid_position(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    # Visualization

    @_api
    def print_world_state(self):
        """Prints a compact visualization of the world state"""
        print(f"\n=== WORLD STATE (Turn {self.turn}) ===")

        # Print grid with coordinates
        print("\nGrid Layout:")
        for y in reversed(range(len(self.grid[0]))):  # Print north at top
            row = []
            for x in range(len(self.grid)):
                cell = self.grid[x][y]
                components = []

                # Agents take priority
                if cell.agents:
                    components.append(f"A{len(cell.agents)}")

                # Terrain features
                if cell.obstacle:
                    components.append("O")
                elif cell.pit:
                    components.append("P")
                elif cell.trap:
                    components.append("T")

                # Item count
                if cell.items:
                    components.append(f"I{len(cell.items)}")

                # Empty cell representation
                if not components:
                    components.append("·")

                row.append("".join(components[:2]))  # Show up to 2 elements
            print(" ".join(f"{cell:4}" for cell in row))

        # Print legend
        print("\nLegend:")
        print("A# - Agents (count)  O - Obstacle  P - Pit")
        print("T - Trap  I# - Items (count)  · - Empty")

        # Print agent statuses
        print("\nActive Agents:")
        for agent in self.agents.values():
            status = "ACTIVE" if agent.can_act() else "INACTIVE"
            print(f"  {agent} ({status}) @ {agent.position}")
            # print(f"{agent.name} ({status}) @ {agent.position}:")
            # print(f"  Health: {agent.health}  Energy: {agent.energy}  ATP: {agent.atp}")
            # print(f"  Inventory: {[item.name for item in agent.inventory]}")
            print(f"   Inventory: {agent.inventory}")
            # print("-" * 40)

    @_api
    def print_world_state2(self):
        print(f"\n=== WORLD STATE (Turn {self.turn}) ===")
        print(f"Dimensions: {self.width}x{self.height}")

        # Grid visualization
        print("\n" + self._grid_visualization())

        # Agent statuses
        print("\nActive Agents:")
        for agent in self.agents.values():
            print(f"  {agent}")
            if agent.inventory:
                print(f"    Inventory: {agent.inventory}")

        print("\n" + "=" * 50)

    def _grid_visualization(self) -> str:
        grid_str = "     " + "    ".join(str(x) for x in range(self.width)) + "\n"
        for y in reversed(range(self.height)):
            row = [f"{y:2} "]
            for x in range(self.width):
                cell = self.grid[x][y]
                elements = []

                # Agents
                if cell.agents:
                    elements.append(f"A{len(cell.agents)}")

                # Terrain
                if cell.pit:
                    elements.append("P")
                elif cell.obstacle:
                    elements.append("O")
                elif cell.trap:
                    elements.append("T")

                # Items
                if cell.items:
                    elements.append(f"I{len(cell.items)}")

                row.append("[{}]".format(",".join(elements[:2]) if elements else "  "))
            grid_str += " ".join(row) + "\n"
        return grid_str


# Example Usage
if __name__ == "__main__":
    world = CellWorld(5, 5)

    # Setup world
    world.add_obstacle(2, 2)
    world.add_trap(1, 1)
    world.add_pit(3, 3)
    world.add_item(0, 0, Item(ItemType.WEAPON, "Sword", 5))
    world.add_item(1, 0, Item(ItemType.FOOD, "Apple", 20))

    # Create agents
    alice = Agent("Alice")
    bob = Agent("Bob")
    world.add_agent(alice, (0, 0))
    world.add_agent(bob, (4, 4))

    # Turn 1
    world.new_turn()
    print("=== INITIAL STATE ===")
    world.print_world_state()

    # Alice's actions
    world.move_agent(alice, Direction.EAST)
    world.pick_item(alice, 0)

    # Turn 2
    world.new_turn()
    print("\n=== AFTER MOVEMENT ===")
    world.move_agent(alice, Direction.EAST)
    world.attack(alice, Direction.EAST)  # Attack empty space
    world.print_world_state()

    # Turn 3 - Combat
    world.new_turn()
    print("\n=== COMBAT TURN ===")
    # Move Alice next to Bob
    world.move_agent(alice, Direction.EAST)
    world.move_agent(alice, Direction.EAST)
    world.move_agent(alice, Direction.NORTH)
    world.move_agent(alice, Direction.NORTH)
    world.attack(alice, Direction.EAST)
    world.print_world_state()
