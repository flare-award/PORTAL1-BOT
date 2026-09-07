"""
Navigation Graph Builder - builds graph from WorldModel
"""
from __future__ import annotations
from typing import List, Optional
import math

from ..world_model.vector import Vector3, Bounds
from ..world_model.model import WorldModel
from ..world_model.surface import Surface
from ..world_model.portal import Portal
from ..spatial.raycast import SpatialRaycaster
from .graph import NavigationGraph, EdgeType

class NavigationGraphBuilder:
    def __init__(self, world_model: WorldModel, raycaster: SpatialRaycaster):
        self.world_model = world_model
        self.raycaster = raycaster

    def build(self, grid_size: float = 128.0, max_step_height: float = 32.0) -> NavigationGraph:
        """
        Build navigation graph:
        1. Create nodes from entity positions (cubes, buttons, doors, exits)
        2. Create nodes from floor surfaces sampled on grid
        3. Connect nodes if path clear and height diff acceptable
        4. Add portal edges if portals active
        5. Add door edges
        """
        graph = NavigationGraph()

        # 1. Add nodes for important entities
        important_positions = []

        if self.world_model.player:
            node = graph.add_node(self.world_model.player.position, area_type="ground")
            important_positions.append((self.world_model.player.position, node.id))

        for cube in self.world_model.cubes.values():
            node = graph.add_node(cube.position, area_type="ground")
            important_positions.append((cube.position, node.id))

        for button in self.world_model.buttons.values():
            node = graph.add_node(button.position, area_type="ground", is_button=True)
            important_positions.append((button.position, node.id))

        for door in self.world_model.doors.values():
            # Door has two sides
            # Approximate: door position + forward offset
            node = graph.add_node(door.position, area_type="ground", is_door=True)
            important_positions.append((door.position, node.id))
            # Add node on other side of door
            other_side = door.position + Vector3(0, 100, 0)  # simplified
            node2 = graph.add_node(other_side, area_type="ground")
            important_positions.append((other_side, node2.id))

        for exit_door in self.world_model.exits.values():
            node = graph.add_node(exit_door.position, area_type="ground")
            important_positions.append((exit_door.position, node.id))

        # 2. Sample floor surfaces to create ground nodes
        floor_surfaces = [s for s in self.world_model.surfaces.values() if s.normal.z > 0.7]  # roughly horizontal floor
        sampled_nodes = []

        for surf in floor_surfaces:
            # Sample grid within bounds
            mins = surf.bounds.mins
            maxs = surf.bounds.maxs
            x_steps = int((maxs.x - mins.x) / grid_size) + 1
            y_steps = int((maxs.y - mins.y) / grid_size) + 1
            # Limit steps to avoid too many nodes
            x_steps = min(x_steps, 10)
            y_steps = min(y_steps, 10)

            for xi in range(x_steps):
                for yi in range(y_steps):
                    x = mins.x + xi * grid_size + grid_size/2
                    y = mins.y + yi * grid_size + grid_size/2
                    z = surf.position.z + 20  # slightly above floor
                    pos = Vector3(x,y,z)
                    if surf.bounds.contains(pos) or surf.bounds.expand(10).contains(pos):
                        # Check if position is free (no entity collision)
                        # For simplicity, add node
                        node = graph.add_node(pos, area_type="ground", room_id=None)
                        sampled_nodes.append((pos, node.id))

        # 3. Connect nodes
        # For each pair of nodes, check if path clear and within reasonable distance
        all_nodes = list(graph.nodes.values())
        max_connection_dist = 300.0

        for i, node_a in enumerate(all_nodes):
            for j in range(i+1, len(all_nodes)):
                node_b = all_nodes[j]
                dist = node_a.position.distance_to(node_b.position)
                if dist > max_connection_dist:
                    continue
                # Height check
                height_diff = abs(node_a.position.z - node_b.position.z)
                if height_diff > max_step_height and dist < 100:
                    # Too high step, need jump or portal
                    # Still allow but with jump edge type if height diff moderate
                    if height_diff <= 64.0:
                        # Check if path clear at elevated height
                        from_elev = node_a.position + Vector3(0,0,10)
                        to_elev = node_b.position + Vector3(0,0,10)
                        if self.raycaster.is_path_clear(from_elev, to_elev):
                            graph.add_edge(node_a.id, node_b.id, edge_type=EdgeType.JUMP)
                    continue

                # Check path clear
                from_pos = node_a.position + Vector3(0,0,10)
                to_pos = node_b.position + Vector3(0,0,10)
                if self.raycaster.is_path_clear(from_pos, to_pos):
                    # Determine edge type
                    edge_type = EdgeType.WALK
                    if height_diff > 20:
                        edge_type = EdgeType.STAIRS if height_diff < 40 else EdgeType.JUMP
                    graph.add_edge(node_a.id, node_b.id, edge_type=edge_type)

        # 4. Add portal edges
        active_portals = [p for p in self.world_model.portals.values() if p.active]
        # Find portal pairs
        blue_portals = [p for p in active_portals if p.portal_type == "blue"]
        orange_portals = [p for p in active_portals if p.portal_type == "orange"]

        for blue in blue_portals:
            for orange in orange_portals:
                if blue.linked_portal_id == orange.id or orange.linked_portal_id == blue.id:
                    # Find closest nodes to each portal
                    blue_node = graph.find_closest_node(blue.position, max_dist=200)
                    orange_node = graph.find_closest_node(orange.position, max_dist=200)
                    if blue_node and orange_node:
                        # Add portal edge both ways with low cost
                        graph.add_edge(blue_node.id, orange_node.id, edge_type=EdgeType.PORTAL, cost=10.0, portal_id=blue.id, bidirectional=True)
                        graph.add_edge(orange_node.id, blue_node.id, edge_type=EdgeType.PORTAL, cost=10.0, portal_id=orange.id, bidirectional=True)

        # 5. Add door edges (require door open)
        for door in self.world_model.doors.values():
            # Find nodes on both sides of door
            # Simplified: find two closest nodes to door that are on opposite sides
            nodes_near_door = []
            for node in all_nodes:
                if node.position.distance_to(door.position) < 200:
                    nodes_near_door.append(node)

            # Connect nodes near door with door edge requiring door entity
            for i in range(len(nodes_near_door)):
                for j in range(i+1, len(nodes_near_door)):
                    n1 = nodes_near_door[i]
                    n2 = nodes_near_door[j]
                    # Check if they are on opposite sides (dot product with door forward?)
                    # Simplified: just add edge with door requirement if path blocked by door
                    # If door is closed, path might be blocked - we still add edge but with requirement
                    if not self.raycaster.is_path_clear(n1.position + Vector3(0,0,10), n2.position + Vector3(0,0,10)):
                        # Path blocked, likely by door
                        graph.add_edge(n1.id, n2.id, edge_type=EdgeType.DOOR, required_entity_id=door.id, bidirectional=True)
                    else:
                        # Path clear even with door closed? Still add door edge as alternative
                        pass

        print(f"[NavBuilder] Built graph: {graph.summary()}")
        return graph

    def update_with_portals(self, graph: NavigationGraph, portals: List[Portal]) -> NavigationGraph:
        """
        Update existing graph with new portal positions
        """
        # Remove old portal edges
        graph.edges = [e for e in graph.edges if e.edge_type != EdgeType.PORTAL]
        # Rebuild adjacency
        for nid in graph.adjacency:
            graph.adjacency[nid] = [e for e in graph.adjacency[nid] if e.edge_type != EdgeType.PORTAL]

        # Add new portal edges
        active_portals = [p for p in portals if p.active]
        blue_portals = [p for p in active_portals if p.portal_type == "blue"]
        orange_portals = [p for p in active_portals if p.portal_type == "orange"]

        for blue in blue_portals:
            for orange in orange_portals:
                if blue.linked_portal_id == orange.id or orange.linked_portal_id == blue.id:
                    blue_node = graph.find_closest_node(blue.position, max_dist=200)
                    orange_node = graph.find_closest_node(orange.position, max_dist=200)
                    if blue_node and orange_node:
                        graph.add_edge(blue_node.id, orange_node.id, edge_type=EdgeType.PORTAL, cost=10.0, portal_id=blue.id, bidirectional=True)

        return graph
