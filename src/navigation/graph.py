"""
Navigation Graph - nodes = reachable positions, edges = possible movements
Supports portal traversal, jump, drop, door, button activation
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import heapq
import math

from ..world_model.vector import Vector3, Bounds

class EdgeType:
    WALK = "walk"
    JUMP = "jump"
    DROP = "drop"
    PORTAL = "portal"
    DOOR = "door"
    BUTTON = "button"
    ELEVATOR = "elevator"
    STAIRS = "stairs"

@dataclass
class NavNode:
    id: int
    position: Vector3
    area_type: str = "ground"  # ground, elevated, platform, hazard
    room_id: Optional[int] = None
    bounds: Optional[Bounds] = None
    is_portal_surface: bool = False
    is_button: bool = False
    is_door: bool = False
    cost_modifier: float = 1.0

    def to_dict(self):
        return {
            "id": self.id,
            "position": self.position.to_tuple(),
            "area_type": self.area_type,
            "room_id": self.room_id,
            "is_portal_surface": self.is_portal_surface,
            "is_button": self.is_button,
            "is_door": self.is_door
        }

@dataclass
class NavEdge:
    from_node: int
    to_node: int
    edge_type: str = EdgeType.WALK
    cost: float = 1.0
    required_entity_id: Optional[int] = None  # e.g., door that must be open
    portal_id: Optional[int] = None  # for portal edges
    bidirectional: bool = True
    traversable: bool = True

    def to_dict(self):
        return {
            "from": self.from_node,
            "to": self.to_node,
            "type": self.edge_type,
            "cost": self.cost,
            "required_entity": self.required_entity_id,
            "portal_id": self.portal_id,
            "bidirectional": self.bidirectional,
            "traversable": self.traversable
        }

class NavigationGraph:
    def __init__(self):
        self.nodes: Dict[int, NavNode] = {}
        self.edges: List[NavEdge] = []
        self.adjacency: Dict[int, List[NavEdge]] = {}  # node_id -> edges
        self._next_node_id = 0

    def add_node(self, position: Vector3, area_type: str = "ground", room_id: Optional[int] = None, **kwargs) -> NavNode:
        node_id = self._next_node_id
        self._next_node_id += 1
        node = NavNode(id=node_id, position=position, area_type=area_type, room_id=room_id, **kwargs)
        self.nodes[node_id] = node
        self.adjacency[node_id] = []
        return node

    def add_edge(self, from_node: int, to_node: int, edge_type: str = EdgeType.WALK, cost: Optional[float] = None, **kwargs) -> NavEdge:
        if from_node not in self.nodes or to_node not in self.nodes:
            raise ValueError(f"Node not found: {from_node} or {to_node}")

        if cost is None:
            # Compute cost as distance * modifier
            from_pos = self.nodes[from_node].position
            to_pos = self.nodes[to_node].position
            dist = from_pos.distance_to(to_pos)
            # Edge type modifiers
            modifiers = {
                EdgeType.WALK: 1.0,
                EdgeType.JUMP: 2.0,
                EdgeType.DROP: 1.5,
                EdgeType.PORTAL: 0.5,  # portals are fast
                EdgeType.DOOR: 1.2,
                EdgeType.BUTTON: 1.0,
                EdgeType.ELEVATOR: 1.5,
                EdgeType.STAIRS: 1.3
            }
            cost = dist * modifiers.get(edge_type, 1.0)

        edge = NavEdge(from_node=from_node, to_node=to_node, edge_type=edge_type, cost=cost, **kwargs)
        self.edges.append(edge)
        self.adjacency[from_node].append(edge)

        if kwargs.get("bidirectional", True):
            # Add reverse edge
            rev_edge = NavEdge(
                from_node=to_node,
                to_node=from_node,
                edge_type=edge_type,
                cost=cost,
                required_entity_id=kwargs.get("required_entity_id"),
                portal_id=kwargs.get("portal_id"),
                bidirectional=True,
                traversable=kwargs.get("traversable", True)
            )
            # For portal edges, reverse should still be portal but direction matters
            # We keep bidirectional but in pathfinding we'll consider both
            self.edges.append(rev_edge)
            self.adjacency[to_node].append(rev_edge)

        return edge

    def remove_node(self, node_id: int):
        self.nodes.pop(node_id, None)
        self.adjacency.pop(node_id, None)
        # Remove edges involving this node
        self.edges = [e for e in self.edges if e.from_node != node_id and e.to_node != node_id]
        # Clean adjacency
        for nid in self.adjacency:
            self.adjacency[nid] = [e for e in self.adjacency[nid] if e.to_node != node_id]

    def get_node(self, node_id: int) -> Optional[NavNode]:
        return self.nodes.get(node_id)

    def get_neighbors(self, node_id: int) -> List[Tuple[NavNode, NavEdge]]:
        result = []
        for edge in self.adjacency.get(node_id, []):
            if not edge.traversable:
                continue
            neighbor = self.nodes.get(edge.to_node)
            if neighbor:
                result.append((neighbor, edge))
        return result

    def find_closest_node(self, position: Vector3, max_dist: float = 500.0) -> Optional[NavNode]:
        closest = None
        min_dist = max_dist
        for node in self.nodes.values():
            dist = node.position.distance_to(position)
            if dist < min_dist:
                min_dist = dist
                closest = node
        return closest

    def find_path(self, from_pos: Vector3, to_pos: Vector3, world_model=None) -> Optional[List[NavNode]]:
        """
        A* pathfinding from from_pos to to_pos
        """
        start_node = self.find_closest_node(from_pos)
        goal_node = self.find_closest_node(to_pos)

        if not start_node or not goal_node:
            # If no nodes near, try to create temporary nodes?
            return None

        # A*
        open_set = []
        heapq.heappush(open_set, (0, start_node.id))
        came_from: Dict[int, Tuple[int, NavEdge]] = {}
        g_score: Dict[int, float] = {nid: float('inf') for nid in self.nodes}
        g_score[start_node.id] = 0
        f_score: Dict[int, float] = {nid: float('inf') for nid in self.nodes}
        f_score[start_node.id] = start_node.position.distance_to(goal_node.position)

        closed_set = set()

        while open_set:
            _, current_id = heapq.heappop(open_set)
            if current_id in closed_set:
                continue
            closed_set.add(current_id)

            if current_id == goal_node.id:
                # Reconstruct path
                path = []
                curr = current_id
                while curr in came_from:
                    path.append(self.nodes[curr])
                    curr, _ = came_from[curr]
                path.append(self.nodes[start_node.id])
                path.reverse()
                return path

            current_g = g_score[current_id]
            for neighbor, edge in self.get_neighbors(current_id):
                # Check if edge requires entity that is not traversable
                if world_model and edge.required_entity_id:
                    # Check door open?
                    ent = world_model.entities.get(edge.required_entity_id)
                    if ent:
                        # If door and not open, skip
                        if hasattr(ent, 'open') and not ent.open:
                            continue
                        if hasattr(ent, 'active') and not ent.active:
                            continue

                tentative_g = current_g + edge.cost
                if tentative_g < g_score[neighbor.id]:
                    came_from[neighbor.id] = (current_id, edge)
                    g_score[neighbor.id] = tentative_g
                    f_score[neighbor.id] = tentative_g + neighbor.position.distance_to(goal_node.position)
                    heapq.heappush(open_set, (f_score[neighbor.id], neighbor.id))

        return None  # No path found

    def to_dict(self):
        return {
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges]
        }

    def summary(self) -> str:
        return f"NavGraph: {len(self.nodes)} nodes, {len(self.edges)} edges"
