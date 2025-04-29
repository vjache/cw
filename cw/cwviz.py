import os

import pygame
import pygame_gui
from pygame.locals import *

from cw import CellWorld, Agent, Item, ItemType, Status
import cw


class CellWorldVisualizer:
    def __init__(self, world: CellWorld, cell_size=40, hud_width=300, chat_height=150):
        self.world = world
        self.cell_size = cell_size
        self.hud_width = hud_width
        self.chat_height = chat_height
        self.selected_agent = None

        # Pygame initialization
        pygame.init()
        self.width = world.width * cell_size + hud_width
        self.height = world.height * cell_size + chat_height
        # Add Retina display support (insert these 2 lines)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK,
                                        pygame.GL_CONTEXT_PROFILE_CORE)
        self.screen = pygame.display.set_mode((self.width, self.height), vsync=1)
        # if 'SDL_VIDEO_CENTERED' in pygame.display.get_driver():
        os.environ['SDL_VIDEO_CENTERED'] = '1'
        pygame.display.set_caption("Cell World Simulation")

        # UI Manager setup
        self.manager = pygame_gui.UIManager((self.width, self.height))
        self.clock = pygame.time.Clock()

        # Create UI elements
        self._create_ui_elements()

        # Color definitions
        self.colors = {
            'grid': (40, 40, 40),
            'background': (20, 20, 20),
            'obstacle': (100, 100, 100),
            'trap': (200, 0, 0),
            'pit': (50, 50, 50),
            'agent': (0, 120, 200),
            'item': (0, 200, 100),
            'text': (255, 255, 255),
            'selection': (255, 255, 0)
        }

    def _create_ui_elements(self):
        grid_height = self.world.height * self.cell_size

        # Stats panel (right side - unchanged)
        self.stats_panel = pygame_gui.elements.UITextBox(
            relative_rect=pygame.Rect(
                (self.world.width * self.cell_size + 10, 10),
                (self.hud_width - 20, grid_height - 20)
            ),
            manager=self.manager,
            html_text="<b>Selected Agent:</b> None"
        )

        # Chat log (full width bottom)
        self.log_window = pygame_gui.elements.UITextBox(
            relative_rect=pygame.Rect(
                (10, grid_height + 10),  # Start from left edge
                (self.width - 20, self.chat_height - 50)  # Use full width
            ),
            manager=self.manager,
            html_text=""
        )

        # Input box (full width bottom)
        self.input_box = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(
                (10, grid_height + self.chat_height - 40),
                (self.width - 100, 40)  # Stretch to right edge
            ),
            manager=self.manager
        )

        # Submit button (right-aligned in bottom panel)
        self.submit_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(
                (self.width - 90, grid_height + self.chat_height - 40),
                (80, 40)
            ),
            text='Submit',
            manager=self.manager
        )

    def _draw_grid(self):
        for x in range(self.world.width):
            for y in range(self.world.height):
                rect = pygame.Rect(
                    x * self.cell_size,
                    (self.world.height - 1 - y) * self.cell_size,
                    self.cell_size - 1,
                    self.cell_size - 1
                )

                cell = self.world.grid[x][y]

                # Base cell color
                if cell.obstacle:
                    color = self.colors['obstacle']
                elif cell.pit:
                    color = self.colors['pit']
                elif cell.trap:
                    color = self.colors['trap']
                else:
                    color = self.colors['background']

                pygame.draw.rect(self.screen, color, rect)

                # Add grid lines (1px border)
                pygame.draw.rect(self.screen, self.colors['grid'], rect, 1)

                # Draw items
                if cell.items:
                    pygame.draw.circle(self.screen, self.colors['item'],
                                       rect.center, self.cell_size // 6)

                # Draw agents
                for agent in cell.agents:
                    pygame.draw.circle(self.screen, self.colors['agent'],
                                       rect.center, self.cell_size // 4)

                # Draw selection
                if self.selected_agent and self.selected_agent.position == (x, y):
                    pygame.draw.rect(self.screen, self.colors['selection'], rect, 3)

    def _draw_hud(self):
        # Stats panel background
        stats_rect = pygame.Rect(
            self.world.width * self.cell_size, 0,
            self.hud_width, self.world.height * self.cell_size
        )
        pygame.draw.rect(self.screen, (30, 30, 30), stats_rect)

        # Update stats panel text
        if self.selected_agent:
            stats_text = [
                f"<b>Agent:</b> {self.selected_agent.name}",
                f"Health: {self.selected_agent.health}",
                f"Energy: {self.selected_agent.energy}",
                f"ATP: {self.selected_agent.atp}",
                f"Status: {self.selected_agent.status}",
                f"Goal: {self.selected_agent.goal}",
                "<b>Inventory:</b>"
            ]
            stats_text += [f"- {item.name} ({item.type.value})" for item in self.selected_agent.inventory]
            self.stats_panel.set_text("<br>".join(stats_text))
        else:
            self.stats_panel.set_text("<b>Selected Agent:</b> None")

    def _draw_cell_info(self, mouse_pos):
        # Only show tooltip in grid area
        grid_width = self.world.width * self.cell_size
        grid_bottom = self.world.height * self.cell_size
        if mouse_pos[1] > grid_bottom or mouse_pos[0] > grid_width:
            return

        x = mouse_pos[0] // self.cell_size
        y = self.world.height - 1 - (mouse_pos[1] // self.cell_size)

        if 0 <= x < self.world.width and 0 <= y < self.world.height:
            cell = self.world.grid[x][y]

            terrain = None
            if cell.obstacle:
                terrain = 'obstacle'
            elif cell.pit:
                terrain = 'pit'
            elif cell.trap:
                terrain = 'trap'

            terrain = f' [{terrain}]' if terrain else ''
            info = [f"Cell: {x},{y}{terrain}"]

            for item in cell.items:
                info.append(f'item: {item.name}')

            for agent in cell.agents:
                info.append(f'agent: {agent.name}')

            if info:
                font = pygame.font.Font(None, 18)
                line_height = 20
                max_line_length = max(len(line) for line in info)
                total_height = len(info) * line_height
                tooltip_width = max(150, max_line_length * 8)  # Approximate text width

                # Calculate initial position
                x_pos = mouse_pos[0] + 10
                y_pos = mouse_pos[1] + 10

                # Adjust horizontal position
                if x_pos + tooltip_width > grid_width:
                    x_pos = max(10, mouse_pos[0] - tooltip_width - 10)

                # Adjust vertical position
                if y_pos + total_height > grid_bottom:
                    y_pos = max(10, mouse_pos[1] - total_height - 10)

                # Draw tooltip background
                tooltip_rect = pygame.Rect(
                    x_pos - 5,
                    y_pos - 5,
                    tooltip_width + 10,
                    total_height + 10
                )
                pygame.draw.rect(self.screen, (40, 40, 40), tooltip_rect)
                pygame.draw.rect(self.screen, (80, 80, 80), tooltip_rect, 1)

                # Draw text
                for line in info:
                    text = font.render(line, True, (255, 255, 255))
                    self.screen.blit(text, (x_pos, y_pos))
                    y_pos += line_height

    def run(self):
        # Enable retina scaling factor (add in run() before main loop)
        if pygame.display.get_driver() == 'cocoa':
            self.screen = pygame.display.get_surface()
            self.screen = pygame.display.set_mode(
                (self.width, self.height),
                vsync=1, flags=pygame.SCALED)
        running = True
        while running:
            time_delta = self.clock.tick(60) / 1000.0
            mouse_pos = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == QUIT:
                    running = False

                if event.type == MOUSEBUTTONDOWN:
                    # Only select agents in grid area
                    if mouse_pos[0] < self.world.width * self.cell_size and \
                            mouse_pos[1] < self.world.height * self.cell_size:
                        x = mouse_pos[0] // self.cell_size
                        y = self.world.height - 1 - (mouse_pos[1] // self.cell_size)
                        cell = self.world.grid[x][y]
                        if cell.agents:
                            self.selected_agent = cell.agents[0]

                if event.type == pygame_gui.UI_BUTTON_PRESSED:
                    if event.ui_element == self.submit_button:
                        goal = self.input_box.get_text()
                        if goal:
                            if self.selected_agent:
                                if self.selected_agent.status == Status.EXEC_GOAL:
                                    self._add_log(f"CWV: Selected agent {self.selected_agent.name} is busy.")
                                else:
                                    self._add_log(f"User to {self.selected_agent.name}: {goal}")
                                    self.selected_agent.set_goal(goal)
                                    self.input_box.set_text("")
                            else:
                                self._add_log(f"CWV: No agent selected. Please select an agent.")

                self.manager.process_events(event)

            for agent_name, agent in self.world.agents.items():
                new_messages = agent.take_goal_log()
                if new_messages:
                    for message in new_messages:
                        self._add_log(f"{agent_name}: {message}")

            self.screen.fill(self.colors['background'])

            with cw.CW_API_LOCK:
                self._draw_grid()
                self._draw_hud()
                self._draw_cell_info(mouse_pos)

            self.manager.update(time_delta)
            self.manager.draw_ui(self.screen)
            pygame.display.flip()

    def _add_log(self, message: str):
        current_text = self.log_window.html_text
        new_text = f"{message}<br>{current_text}"
        self.log_window.set_text(new_text)


# Example usage
if __name__ == "__main__":
    world = CellWorld(20, 20)

    # Add world content
    world.add_obstacle(5, 5)
    world.add_trap(3, 3)
    world.add_item(2, 2, Item(ItemType.FOOD, "Apple", 20))
    world.add_item(4, 4, Item(ItemType.WEAPON, "Sword", 5))
    world.add_item(3, 4, Item(ItemType.RESOURCE, "Stone", 10))

    # Create agents
    researcher = Agent("AI Researcher")
    assistant = Agent("Assistant")
    world.add_agent(researcher, (0, 0))
    world.add_agent(assistant, (7, 7))

    world.new_turn(1000)

    def run_agent(agent):
        from cw import Direction
        from time import sleep
        agent.append_goal_log('Start goal execution.')
        for _ in range(10):
            world.move_agent(agent, Direction.EAST)
            sleep(0.1)
        agent.append_goal_log("Task completed.")
        agent.set_idle()


    def start_agent_goal(agent):
        from threading import Thread
        thread = Thread(target=run_agent, args=[agent])
        thread.start()

    researcher.on_goal_set = start_agent_goal
    assistant.on_goal_set = start_agent_goal
    # Initialize and run visualizer
    vis = CellWorldVisualizer(world, cell_size=30, chat_height=200)
    vis.run()
