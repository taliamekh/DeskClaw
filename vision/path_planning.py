import heapq
import math
from typing import Dict, List, Optional, Sequence, Tuple

Point = Tuple[float, float]


def _clamp_point(point: Point, bounds: Tuple[float, float, float, float]) -> Point:
    min_x, min_y, max_x, max_y = bounds
    return (
        float(min(max(point[0], min_x), max_x)),
        float(min(max(point[1], min_y), max_y)),
    )


def adjust_endpoints_for_standoff(
    start: Point,
    goal: Point,
    bounds: Tuple[float, float, float, float],
    start_offset: float,
    goal_offset: float,
) -> Tuple[Point, Point]:
    """Move path start/goal inward so robot does not start/end exactly on detected centers."""
    dx = goal[0] - start[0]
    dy = goal[1] - start[1]
    distance = math.hypot(dx, dy)

    if distance < 1e-6:
        return _clamp_point(start, bounds), _clamp_point(goal, bounds)

    ux = dx / distance
    uy = dy / distance

    adjusted_start = (start[0] + ux * max(start_offset, 0.0), start[1] + uy * max(start_offset, 0.0))
    adjusted_goal = (goal[0] - ux * max(goal_offset, 0.0), goal[1] - uy * max(goal_offset, 0.0))

    return _clamp_point(adjusted_start, bounds), _clamp_point(adjusted_goal, bounds)


def compute_waypoint_headings(path: Sequence[Point], fallback_heading: float = 0.0) -> List[float]:
    """Return desired heading (deg) at each waypoint toward the next waypoint."""
    if not path:
        return []

    headings: List[float] = []
    for i in range(len(path) - 1):
        dx = path[i + 1][0] - path[i][0]
        dy = path[i + 1][1] - path[i][1]
        headings.append(float(math.degrees(math.atan2(dy, dx))))

    headings.append(headings[-1] if headings else float(fallback_heading))
    return headings


def select_target_detection(detections: Sequence[Dict], target_name: str) -> Optional[Dict]:
    """Return the highest-confidence detection whose label matches the requested target name."""
    target = target_name.strip().lower()
    if not target:
        return None

    matches = [
        d
        for d in detections
        if target in str(d.get("label", "")).lower()
    ]
    if not matches:
        return None

    return max(matches, key=lambda d: float(d.get("confidence", 0.0)))


def _to_grid(point: Point, bounds: Tuple[float, float, float, float], resolution: float) -> Tuple[int, int]:
    min_x, min_y, _, _ = bounds
    return (
        int(round((point[0] - min_x) / resolution)),
        int(round((point[1] - min_y) / resolution)),
    )


def _to_world(node: Tuple[int, int], bounds: Tuple[float, float, float, float], resolution: float) -> Point:
    min_x, min_y, _, _ = bounds
    return (min_x + node[0] * resolution, min_y + node[1] * resolution)


def _within_bounds(point: Point, bounds: Tuple[float, float, float, float]) -> bool:
    min_x, min_y, max_x, max_y = bounds
    return min_x <= point[0] <= max_x and min_y <= point[1] <= max_y


def _is_blocked(point: Point, obstacles: Sequence[Dict]) -> bool:
    for obstacle in obstacles:
        ox, oy = obstacle["center"]
        radius = obstacle["radius"]
        if math.hypot(point[0] - ox, point[1] - oy) <= radius:
            return True
    return False


def plan_path_astar(
    start: Point,
    goal: Point,
    obstacles: Sequence[Dict],
    bounds: Tuple[float, float, float, float],
    resolution: float = 2.5,
) -> List[Point]:
    """Plan a 2D path using A* over a quantized grid in the chosen coordinate frame."""
    if not (_within_bounds(start, bounds) and _within_bounds(goal, bounds)):
        return []

    if _is_blocked(start, obstacles) or _is_blocked(goal, obstacles):
        return []

    start_node = _to_grid(start, bounds, resolution)
    goal_node = _to_grid(goal, bounds, resolution)

    open_heap: List[Tuple[float, Tuple[int, int]]] = []
    heapq.heappush(open_heap, (0.0, start_node))

    came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
    g_score: Dict[Tuple[int, int], float] = {start_node: 0.0}

    neighbors = [
        (-1, 0),
        (1, 0),
        (0, -1),
        (0, 1),
        (-1, -1),
        (-1, 1),
        (1, -1),
        (1, 1),
    ]

    max_expansions = 20000
    expansions = 0

    while open_heap and expansions < max_expansions:
        _, current = heapq.heappop(open_heap)
        expansions += 1

        if current == goal_node:
            path_nodes = [current]
            while current in came_from:
                current = came_from[current]
                path_nodes.append(current)
            path_nodes.reverse()
            return [_to_world(node, bounds, resolution) for node in path_nodes]

        for dx, dy in neighbors:
            nxt = (current[0] + dx, current[1] + dy)
            nxt_world = _to_world(nxt, bounds, resolution)
            if not _within_bounds(nxt_world, bounds):
                continue
            if _is_blocked(nxt_world, obstacles):
                continue

            step_cost = math.sqrt(2.0) if dx != 0 and dy != 0 else 1.0
            tentative_g = g_score[current] + step_cost

            if tentative_g < g_score.get(nxt, float("inf")):
                came_from[nxt] = current
                g_score[nxt] = tentative_g
                heuristic = math.hypot(goal_node[0] - nxt[0], goal_node[1] - nxt[1])
                heapq.heappush(open_heap, (tentative_g + heuristic, nxt))

    return []

