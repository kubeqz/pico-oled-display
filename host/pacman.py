"""Self-playing Pac-Man mode for PicoLED."""
from __future__ import annotations

import math
import random
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from picoled import PicoLED


def run(d: PicoLED, width: int, height: int) -> None:
    start = (1, 1)
    directions = ((1, 0), (0, 1), (-1, 0), (0, -1))

    def generate_level(ghost_count):
        grid_width = width // 8
        grid_height = height // 8 - 1
        maze = [["#"] * grid_width for _ in range(grid_height)]
        maze[start[1]][start[0]] = "."
        visited = {start}
        stack = [start]

        while stack:
            x, y = stack[-1]
            neighbors = [
                (x + dx * 2, y + dy * 2)
                for dx, dy in directions
                if 1 <= x + dx * 2 < grid_width - 1
                and 1 <= y + dy * 2 < grid_height - 1
                and (x + dx * 2, y + dy * 2) not in visited
            ]
            if not neighbors:
                stack.pop()
                continue
            nx, ny = random.choice(neighbors)
            maze[(y + ny) // 2][(x + nx) // 2] = "."
            maze[ny][nx] = "."
            visited.add((nx, ny))
            stack.append((nx, ny))

        walls = {
            (x, y)
            for y, row in enumerate(maze)
            for x, tile in enumerate(row)
            if tile == "#"
        }
        floor = {
            (x, y)
            for y, row in enumerate(maze)
            for x, tile in enumerate(row)
            if tile == "."
        }

        def find_components(tiles):
            remaining = set(tiles)
            components = []
            while remaining:
                component = {remaining.pop()}
                queue = list(component)
                for current in queue:
                    for dx, dy in directions:
                        neighbor = (current[0] + dx, current[1] + dy)
                        if neighbor in remaining:
                            remaining.remove(neighbor)
                            component.add(neighbor)
                            queue.append(neighbor)
                components.append(component)
            return components

        ghost_areas = []
        ghost_sides = (
            {tile for tile in floor if tile[0] <= grid_width // 2 - 1},
            {tile for tile in floor if tile[0] >= grid_width // 2 + 1},
        )
        for side in ghost_sides:
            ghost_areas.append(max(find_components(side), key=len))
        ghost_areas = random.sample(ghost_areas, k=ghost_count)

        ghost_starts = [
            random.choice(tuple(area - {start})) if len(area) > 1 else random.choice(tuple(area))
            for area in ghost_areas
        ]
        ghost_targets = [
            random.choice(tuple(area - {ghost}))
            if len(area) > 1
            else ghost
            for area, ghost in zip(ghost_areas, ghost_starts)
        ]
        return walls, floor - {start}, ghost_areas, ghost_starts, ghost_targets

    def next_step(position, targets, allowed=None):
        if not targets:
            return position
        queue = [(position, position)]
        visited = {position}
        for current, first_step in queue:
            if current in targets:
                return first_step
            for dx, dy in directions:
                neighbor = (current[0] + dx, current[1] + dy)
                if neighbor not in walls and neighbor not in visited and (allowed is None or neighbor in allowed):
                    visited.add(neighbor)
                    queue.append((neighbor, neighbor if current == position else first_step))
        return position

    img, draw = d.new_canvas()
    player = start
    player_direction = (1, 0)
    walls, pellets, ghost_areas, ghost_starts, ghost_targets = generate_level(2)
    ghosts = list(ghost_starts)
    frames_per_tile = 6
    frame_interval = 1 / 30
    frame_number = 0

    def render(player_position, ghost_positions):
        nonlocal frame_number
        draw.rectangle((0, 0, width - 1, height - 1), fill=0)
        for x, y in walls:
            draw.rectangle((x * 8 + 1, y * 8 + 1, x * 8 + 6, y * 8 + 6), fill=1)
        for x, y in pellets:
            cx, cy = x * 8 + 4, y * 8 + 4
            draw.ellipse((cx - 1, cy - 1, cx + 1, cy + 1), fill=1)

        for gx, gy in ghost_positions:
            cx, cy = round(gx * 8 + 4), round(gy * 8 + 4)
            draw.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=1)
            draw.rectangle((cx - 3, cy, cx + 3, cy + 3), fill=1)
            draw.ellipse((cx - 2, cy - 1, cx - 1, cy + 1), fill=0)
            draw.ellipse((cx + 1, cy - 1, cx + 2, cy + 1), fill=0)

        px, py = round(player_position[0] * 8 + 4), round(player_position[1] * 8 + 4)
        draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill=1)
        if frame_number % 6 < 3:
            angle = math.atan2(player_direction[1], player_direction[0])
            mouth = [
                (px, py),
                (px + round(4 * math.cos(angle - 0.65)), py + round(4 * math.sin(angle - 0.65))),
                (px + round(4 * math.cos(angle + 0.65)), py + round(4 * math.sin(angle + 0.65))),
            ]
            draw.polygon(mouth, fill=0)

        d.show_image(img)
        frame_number += 1

    while True:
        next_player = next_step(player, pellets)
        if next_player != player:
            player_direction = (next_player[0] - player[0], next_player[1] - player[1])
        next_ghosts = []
        for index, (ghost, area) in enumerate(zip(ghosts, ghost_areas)):
            if next_player in area:
                target = next_player
            else:
                if ghost == ghost_targets[index] and len(area) > 1:
                    ghost_targets[index] = random.choice(tuple(area - {ghost}))
                target = ghost_targets[index]
            next_ghosts.append(next_step(ghost, {target}, allowed=area))

        for frame in range(1, frames_per_tile + 1):
            frame_start = time.monotonic()
            progress = frame / frames_per_tile
            player_position = (
                player[0] + (next_player[0] - player[0]) * progress,
                player[1] + (next_player[1] - player[1]) * progress,
            )
            ghost_positions = [
                (
                    ghosts[i][0] + (next_ghosts[i][0] - ghosts[i][0]) * progress,
                    ghosts[i][1] + (next_ghosts[i][1] - ghosts[i][1]) * progress,
                )
                for i in range(len(ghosts))
            ]
            render(player_position, ghost_positions)
            time.sleep(max(0, frame_interval - (time.monotonic() - frame_start)))

        player = next_player
        ghosts = [ghost for ghost in next_ghosts if ghost != player]
        ghost_areas = [area for i, area in enumerate(ghost_areas) if next_ghosts[i] != player]
        ghost_starts = [ghost for i, ghost in enumerate(ghost_starts) if next_ghosts[i] != player]
        ghost_targets = [target for i, target in enumerate(ghost_targets) if next_ghosts[i] != player]
        if player in pellets:
            pellets.remove(player)

        if not pellets:
            draw.rectangle((0, 0, width - 1, height - 1), fill=0)
            draw.text((40, 27), "YOU WIN!", fill=1)
            d.show_image(img)
            time.sleep(1)
            walls, pellets, ghost_areas, ghost_starts, ghost_targets = generate_level(len(ghosts))
            ghosts = list(ghost_starts)
            player = start
            player_direction = (1, 0)


if __name__ == "__main__":
    from picoled import HEIGHT, WIDTH, PicoLED

    with PicoLED() as device:
        run(device, WIDTH, HEIGHT)
