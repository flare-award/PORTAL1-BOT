"""
Puzzle Solver / Action Planner - creates plan from current world state and goal
Generates abstract actions: MoveTo, LookAt, PickUp, Drop, PlacePortal, etc.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum

from ..world_model.vector import Vector3, QAngle
from ..world_model.model import WorldModel, Goal
from ..world_model.entities import Entity, Cube, Button, Door
from ..world_model.surface import Surface
from ..world_model.portal import Portal
from ..spatial.raycast import SpatialRaycaster
from ..spatial.queries import SpatialQuerySystem
from ..navigation.graph import NavigationGraph
from .object_relationships import RelationshipGraph

class ActionType(Enum):
    MOVE_TO = "move_to"
    LOOK_AT = "look_at"
    JUMP = "jump"
    CROUCH = "crouch"
    PICK_UP = "pick_up"
    DROP = "drop"
    PLACE_PORTAL = "place_portal"
    ENTER_PORTAL = "enter_portal"
    PRESS_BUTTON = "press_button"
    WAIT = "wait"
    INTERACT = "interact"
    OPEN_DOOR = "open_door"

@dataclass
class AbstractAction:
    type: ActionType
    target_id: Optional[int] = None
    target_position: Optional[Vector3] = None
    target_normal: Optional[Vector3] = None
    portal_type: Optional[str] = None  # blue/orange
    surface_id: Optional[int] = None
    description: str = ""
    preconditions: List[str] = field(default_factory=list)
    expected_result: str = ""

    def to_dict(self):
        return {
            "type": self.type.value,
            "target_id": self.target_id,
            "target_position": self.target_position.to_tuple() if self.target_position else None,
            "target_normal": self.target_normal.to_tuple() if self.target_normal else None,
            "portal_type": self.portal_type,
            "surface_id": self.surface_id,
            "description": self.description
        }

class ActionPlanner:
    def __init__(self,
                 world_model: WorldModel,
                 spatial_queries: SpatialQuerySystem,
                 nav_graph: NavigationGraph,
                 relationship_graph: RelationshipGraph,
                 raycaster: SpatialRaycaster):
        self.world_model = world_model
        self.spatial = spatial_queries
        self.nav_graph = nav_graph
        self.relationships = relationship_graph
        self.raycaster = raycaster

    def update_world_model(self, world_model: WorldModel):
        self.world_model = world_model
        self.spatial.update_world_model(world_model)

    def plan(self, goal: Goal) -> List[AbstractAction]:
        """
        Create plan for given goal
        """
        if goal.type == "reach_exit":
            return self._plan_reach_exit(goal)
        elif goal.type == "get_cube":
            return self._plan_get_cube(goal)
        elif goal.type == "activate_button":
            return self._plan_activate_button(goal)
        elif goal.type == "open_door":
            return self._plan_open_door(goal)
        elif goal.type == "place_portal":
            return self._plan_place_portal(goal)
        elif goal.type == "reach_position":
            return self._plan_reach_position(goal)
        elif goal.type == "explore":
            return self._plan_explore(goal)
        else:
            return self._plan_reach_position(goal)

    def _plan_reach_exit(self, goal: Goal) -> List[AbstractAction]:
        actions = []
        exit_pos = goal.target_position
        if not exit_pos and goal.target_id:
            ent = self.world_model.entities.get(goal.target_id)
            if ent:
                exit_pos = ent.position

        if not exit_pos:
            return actions

        # Check if path exists
        if self.world_model.player:
            # Find path via nav graph
            path = self.nav_graph.find_path(self.world_model.player.position, exit_pos, self.world_model)
            if path:
                # Convert path to MoveTo actions
                for node in path[1:]:  # skip start
                    actions.append(AbstractAction(
                        type=ActionType.MOVE_TO,
                        target_position=node.position,
                        description=f"Move to nav node {node.id} at {node.position}"
                    ))
            else:
                # No path, need portals?
                # Try to find portal placement
                portal_actions = self._plan_portal_to_reach(exit_pos)
                actions.extend(portal_actions)
                # Then move to exit
                actions.append(AbstractAction(
                    type=ActionType.MOVE_TO,
                    target_position=exit_pos,
                    description=f"Move to exit at {exit_pos}"
                ))

        if not actions:
            actions.append(AbstractAction(
                type=ActionType.MOVE_TO,
                target_position=exit_pos,
                description=f"Move to exit at {exit_pos}"
            ))

        return actions

    def _plan_get_cube(self, goal: Goal) -> List[AbstractAction]:
        actions = []
        cube = self.world_model.cubes.get(goal.target_id) if goal.target_id else None
        if not cube:
            # Find nearest cube
            cube = self.spatial.get_nearest_cube()
            if not cube:
                return actions

        target_pos = cube.position

        # Check if cube is elevated
        if self.world_model.player:
            height_diff = target_pos.z - self.world_model.player.position.z
            if height_diff > 64:
                # Need portal
                portal_actions = self._plan_portal_to_reach(target_pos)
                actions.extend(portal_actions)

        # Move to cube
        if self.world_model.player:
            path = self.nav_graph.find_path(self.world_model.player.position, target_pos, self.world_model)
            if path:
                for node in path[1:]:
                    actions.append(AbstractAction(
                        type=ActionType.MOVE_TO,
                        target_position=node.position,
                        description=f"Move to node {node.id} towards cube"
                    ))
            else:
                actions.append(AbstractAction(
                    type=ActionType.MOVE_TO,
                    target_position=target_pos,
                    description=f"Move to cube {cube.id} at {target_pos}"
                ))

        # Look at cube
        actions.append(AbstractAction(
            type=ActionType.LOOK_AT,
            target_id=cube.id,
            target_position=target_pos,
            description=f"Look at cube {cube.id}"
        ))

        # Pick up cube
        actions.append(AbstractAction(
            type=ActionType.PICK_UP,
            target_id=cube.id,
            target_position=target_pos,
            description=f"Pick up cube {cube.id}"
        ))

        return actions

    def _plan_activate_button(self, goal: Goal) -> List[AbstractAction]:
        actions = []
        button = self.world_model.buttons.get(goal.target_id) if goal.target_id else None
        if not button:
            button = self.spatial.get_nearest_button()
            if not button:
                return actions

        # Check if button requires cube
        deps = self.relationships.get_dependencies(button.id)
        cube_needed = None
        for dep_id in deps:
            ent = self.world_model.entities.get(dep_id)
            if ent and "cube" in ent.classname:
                cube_needed = self.world_model.cubes.get(dep_id)
                break

        if cube_needed:
            # Check if cube is on button already
            if cube_needed.position.distance_to(button.position) > 50:
                # Need to get cube first
                get_cube_goal = Goal(type="get_cube", target_id=cube_needed.id, target_position=cube_needed.position)
                actions.extend(self._plan_get_cube(get_cube_goal))

                # Move to button with cube
                actions.append(AbstractAction(
                    type=ActionType.MOVE_TO,
                    target_id=button.id,
                    target_position=button.position,
                    description=f"Move to button {button.id} with cube"
                ))

                # Drop cube on button
                actions.append(AbstractAction(
                    type=ActionType.DROP,
                    target_id=button.id,
                    target_position=button.position,
                    description=f"Place cube {cube_needed.id} on button {button.id}"
                ))

                # Wait for door
                actions.append(AbstractAction(
                    type=ActionType.WAIT,
                    description="Wait for button to activate and door to open",
                    expected_result="Button pressed, door open"
                ))
                return actions

        # Button doesn't need cube or cube already there, just move to it
        if self.world_model.player:
            path = self.nav_graph.find_path(self.world_model.player.position, button.position, self.world_model)
            if path:
                for node in path[1:]:
                    actions.append(AbstractAction(
                        type=ActionType.MOVE_TO,
                        target_position=node.position,
                        description=f"Move to node {node.id} towards button"
                    ))
            else:
                actions.append(AbstractAction(
                    type=ActionType.MOVE_TO,
                    target_id=button.id,
                    target_position=button.position,
                    description=f"Move to button {button.id}"
                ))

        # Press button (in Portal 1, floor button is pressed by standing or cube, not E)
        # But for wall button, need interact
        actions.append(AbstractAction(
            type=ActionType.PRESS_BUTTON,
            target_id=button.id,
            target_position=button.position,
            description=f"Press button {button.id}"
        ))

        return actions

    def _plan_open_door(self, goal: Goal) -> List[AbstractAction]:
        actions = []
        door = self.world_model.doors.get(goal.target_id) if goal.target_id else None
        if not door:
            return actions

        # Find what controls door
        deps = self.relationships.get_dependencies(door.id)
        for dep_id in deps:
            dep_ent = self.world_model.entities.get(dep_id)
            if dep_ent and "button" in dep_ent.classname:
                button_goal = Goal(type="activate_button", target_id=dep_id, target_position=dep_ent.position)
                actions.extend(self._plan_activate_button(button_goal))
                return actions

        # No button, try to move through door
        actions.append(AbstractAction(
            type=ActionType.MOVE_TO,
            target_id=door.id,
            target_position=door.position,
            description=f"Move to door {door.id}"
        ))
        actions.append(AbstractAction(
            type=ActionType.OPEN_DOOR,
            target_id=door.id,
            description=f"Open door {door.id}"
        ))

        return actions

    def _plan_place_portal(self, goal: Goal) -> List[AbstractAction]:
        actions = []
        target_pos = goal.target_position
        if not target_pos:
            return actions

        # Find portalable surfaces
        # For simplicity, find one near player and one near target

        if not self.world_model.player:
            return actions

        player_pos = self.world_model.player.position

        # Find surface near player for orange portal (floor)
        candidates_near_player = self.raycaster.find_portal_placement_candidates(player_pos, max_dist=500)
        # Prefer floor or wall near player
        floor_near_player = [s for s in candidates_near_player if s.normal.z > 0.5]  # floor
        wall_near_player = [s for s in candidates_near_player if abs(s.normal.z) < 0.5]

        # Find surface near target for blue portal
        candidates_near_target = self.raycaster.find_portal_placement_candidates(target_pos, max_dist=500)

        if not candidates_near_player or not candidates_near_target:
            # Try any portalable surfaces
            all_portalable = [s for s in self.world_model.surfaces.values() if s.portalable]
            if len(all_portalable) >= 2:
                surf1 = all_portalable[0]
                surf2 = all_portalable[1]
            else:
                return actions
        else:
            surf1 = candidates_near_player[0] if candidates_near_player else None
            surf2 = candidates_near_target[0] if candidates_near_target else None
            if not surf1 or not surf2:
                return actions

        # Place blue portal near target
        actions.append(AbstractAction(
            type=ActionType.LOOK_AT,
            target_position=surf2.position,
            target_normal=surf2.normal,
            surface_id=surf2.id,
            description=f"Look at surface {surf2.id} near target for blue portal"
        ))
        actions.append(AbstractAction(
            type=ActionType.PLACE_PORTAL,
            target_position=surf2.position,
            target_normal=surf2.normal,
            portal_type="blue",
            surface_id=surf2.id,
            description=f"Place blue portal on surface {surf2.id} at {surf2.position}"
        ))

        # Place orange portal near player
        actions.append(AbstractAction(
            type=ActionType.LOOK_AT,
            target_position=surf1.position,
            target_normal=surf1.normal,
            surface_id=surf1.id,
            description=f"Look at surface {surf1.id} near player for orange portal"
        ))
        actions.append(AbstractAction(
            type=ActionType.PLACE_PORTAL,
            target_position=surf1.position,
            target_normal=surf1.normal,
            portal_type="orange",
            surface_id=surf1.id,
            description=f"Place orange portal on surface {surf1.id} at {surf1.position}"
        ))

        # Enter orange portal to get to blue
        # Find orange portal entity after placement (will be created)
        actions.append(AbstractAction(
            type=ActionType.ENTER_PORTAL,
            portal_type="orange",
            description="Enter orange portal to reach elevated area"
        ))

        return actions

    def _plan_portal_to_reach(self, target_pos: Vector3) -> List[AbstractAction]:
        goal = Goal(type="place_portal", target_position=target_pos)
        return self._plan_place_portal(goal)

    def _plan_reach_position(self, goal: Goal) -> List[AbstractAction]:
        actions = []
        target_pos = goal.target_position
        if not target_pos:
            return actions

        if self.world_model.player:
            path = self.nav_graph.find_path(self.world_model.player.position, target_pos, self.world_model)
            if path:
                for node in path[1:]:
                    actions.append(AbstractAction(
                        type=ActionType.MOVE_TO,
                        target_position=node.position,
                        description=f"Move to {node.position}"
                    ))
            else:
                # Try portal
                portal_actions = self._plan_portal_to_reach(target_pos)
                if portal_actions:
                    actions.extend(portal_actions)
                actions.append(AbstractAction(
                    type=ActionType.MOVE_TO,
                    target_position=target_pos,
                    description=f"Move to {target_pos}"
                ))
        else:
            actions.append(AbstractAction(
                type=ActionType.MOVE_TO,
                target_position=target_pos,
                description=f"Move to {target_pos}"
            ))

        return actions

    def _plan_explore(self, goal: Goal) -> List[AbstractAction]:
        actions = []
        # Simple explore: move to random unvisited area or nearest surface
        if self.world_model.player:
            # Find farthest surface
            surfaces = list(self.world_model.surfaces.values())
            if surfaces:
                farthest = max(surfaces, key=lambda s: s.position.distance_to(self.world_model.player.position))
                actions.append(AbstractAction(
                    type=ActionType.MOVE_TO,
                    target_position=farthest.position,
                    description=f"Explore towards surface {farthest.id}"
                ))
        return actions
