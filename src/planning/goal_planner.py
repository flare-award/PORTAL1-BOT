"""
Goal Planner - determines current goal based on world state
"""
from __future__ import annotations
from typing import List, Optional
from ..world_model.model import WorldModel, Goal
from ..world_model.vector import Vector3
from .object_relationships import RelationshipGraph

class GoalPlanner:
    def __init__(self, world_model: WorldModel, relationship_graph: RelationshipGraph):
        self.world_model = world_model
        self.relationship_graph = relationship_graph
        self.current_goal: Optional[Goal] = None

    def update_world_model(self, world_model: WorldModel):
        self.world_model = world_model

    def get_current_goal(self) -> Optional[Goal]:
        """
        Determine the most important goal:
        1. If dead, goal is to respawn / survive (not applicable in Portal, but handle)
        2. If exit exists and reachable, goal is reach_exit
        3. If door blocks exit, goal is open_door
        4. If button not pressed, goal is activate_button
        5. If cube needed for button, goal is get_cube
        6. If elevated area with cube, goal is place_portal to reach it
        """
        # Check if player alive
        if self.world_model.player and not self.world_model.player.alive:
            return Goal(type="survive", description="Player died, need to recover", priority=100)

        # Find exit
        if self.world_model.exits:
            exit_door = next(iter(self.world_model.exits.values()))
            # Check if behind door
            if exit_door.behind_door_id:
                door = self.world_model.doors.get(exit_door.behind_door_id)
                if door and not door.open:
                    # Need to open door
                    # Find button controlling door
                    buttons = [b for b in self.world_model.buttons.values() if door.id in b.connected_door_ids or door.id in [rel.target_id for rel in self.relationship_graph.get_relationships_from(door.id)]]
                    # Actually get dependencies
                    deps = self.relationship_graph.get_dependencies(door.id)
                    for dep_id in deps:
                        dep_ent = self.world_model.entities.get(dep_id)
                        if dep_ent and "button" in dep_ent.classname:
                            button = self.world_model.buttons.get(dep_id)
                            if button and not button.pressed:
                                # Check if cube on button?
                                # Find cube that should be on button
                                cube_deps = self.relationship_graph.get_dependencies(button.id)
                                for cube_dep_id in cube_deps:
                                    cube_ent = self.world_model.entities.get(cube_dep_id)
                                    if cube_ent and "cube" in cube_ent.classname:
                                        cube = self.world_model.cubes.get(cube_dep_id)
                                        if cube:
                                            # Is cube already on button?
                                            dist = cube.position.distance_to(button.position)
                                            if dist > 50:
                                                # Need to get cube
                                                return Goal(
                                                    type="get_cube",
                                                    target_id=cube.id,
                                                    target_position=cube.position,
                                                    description=f"Get cube {cube.id} for button {button.id}",
                                                    priority=80
                                                )
                                # If cube already there or no cube needed, activate button
                                return Goal(
                                    type="activate_button",
                                    target_id=button.id,
                                    target_position=button.position,
                                    description=f"Activate button {button.id} to open door {door.id}",
                                    priority=90
                                )
                    # If no button found, try to open door directly
                    return Goal(
                        type="open_door",
                        target_id=door.id,
                        target_position=door.position,
                        description=f"Open door {door.id}",
                        priority=85
                    )

            # If exit not behind door or door open, goal is reach exit
            return Goal(
                type="reach_exit",
                target_id=exit_door.id,
                target_position=exit_door.position,
                description="Reach exit",
                priority=100
            )

        # No exit defined, check for any button not pressed
        for button in self.world_model.buttons.values():
            if not button.pressed:
                # Check if needs cube
                deps = self.relationship_graph.get_dependencies(button.id)
                for dep_id in deps:
                    dep_ent = self.world_model.entities.get(dep_id)
                    if dep_ent and "cube" in dep_ent.classname:
                        cube = self.world_model.cubes.get(dep_id)
                        if cube and cube.position.distance_to(button.position) > 50:
                            return Goal(
                                type="get_cube",
                                target_id=cube.id,
                                target_position=cube.position,
                                description=f"Get cube {cube.id} for button {button.id}",
                                priority=80
                            )
                return Goal(
                    type="activate_button",
                    target_id=button.id,
                    target_position=button.position,
                    description=f"Activate button {button.id}",
                    priority=70
                )

        # Check for cubes that are on elevated platforms (need portal)
        if self.world_model.player:
            for cube in self.world_model.cubes.values():
                height_diff = cube.position.z - self.world_model.player.position.z
                if height_diff > 64:
                    # Need portal to reach
                    return Goal(
                        type="place_portal",
                        target_id=cube.id,
                        target_position=cube.position,
                        description=f"Place portal to reach elevated cube {cube.id}",
                        priority=60
                    )

        # Default: explore or reach some position
        # Find any door not open
        for door in self.world_model.doors.values():
            if not door.open:
                return Goal(
                    type="open_door",
                    target_id=door.id,
                    target_position=door.position,
                    description=f"Open door {door.id}",
                    priority=50
                )

        return Goal(type="explore", description="Explore area", priority=10)

    def get_goal_chain(self, final_goal: Goal) -> List[Goal]:
        """
        Given final goal, resolve dependency chain into sequence of goals
        Example: reach_exit -> open_door -> activate_button -> get_cube
        Returns list in execution order (first to last)
        """
        if not final_goal.target_id:
            return [final_goal]

        dep_order = self.relationship_graph.resolve_dependency_order(final_goal.target_id)
        # dep_order is from dependencies first to goal last
        # Convert to Goals
        goals = []
        for ent_id in dep_order:
            if ent_id == final_goal.target_id:
                goals.append(final_goal)
            else:
                ent = self.world_model.entities.get(ent_id)
                if not ent:
                    continue
                if "cube" in ent.classname:
                    goals.append(Goal(
                        type="get_cube",
                        target_id=ent_id,
                        target_position=ent.position,
                        description=f"Get cube {ent_id}",
                        priority=50
                    ))
                elif "button" in ent.classname:
                    goals.append(Goal(
                        type="activate_button",
                        target_id=ent_id,
                        target_position=ent.position,
                        description=f"Activate button {ent_id}",
                        priority=60
                    ))
                elif "door" in ent.classname:
                    goals.append(Goal(
                        type="open_door",
                        target_id=ent_id,
                        target_position=ent.position,
                        description=f"Open door {ent_id}",
                        priority=70
                    ))

        # If final goal not in dep_order (e.g., no relationship), add it
        if final_goal not in goals:
            goals.append(final_goal)

        return goals
