"""
Perception / Interpretation - converts raw GameStateProvider data to semantic WorldModel
Classifies entities, builds rooms, determines goals, etc.
"""
from __future__ import annotations
from typing import List, Dict, Optional
from ..world_model.model import WorldModel, Goal
from ..world_model.vector import Vector3, Bounds
from ..world_model.surface import Surface, Room
from ..world_model.entities import Entity, Cube, Button, Door, Turret, ExitDoor
from ..game_state.provider import GameStateProvider
from ..planning.object_relationships import RelationshipGraph

class WorldInterpreter:
    def __init__(self, provider: GameStateProvider):
        self.provider = provider

    def interpret(self) -> WorldModel:
        """
        Build WorldModel from provider data with semantic interpretation
        """
        raw_model = self.provider.get_world_model()

        # Classify and enrich
        model = self._enrich_model(raw_model)

        # Build rooms
        model.rooms = self._build_rooms(model)

        # Determine goals
        model.goals = self._determine_goals(model)

        # Build connections
        model.connections = self._build_connections(model)

        return model

    def _enrich_model(self, model: WorldModel) -> WorldModel:
        # Already typed via provider, but ensure relationships
        # Check for companion cube (special material or name)
        for cube in model.cubes.values():
            if "companion" in cube.classname.lower() or cube.properties.get("targetname","").lower().find("companion") != -1:
                cube.is_companion = True

        # Check button states based on cube positions
        for button in model.buttons.values():
            # Check if any cube is on button
            for cube in model.cubes.values():
                dist = cube.position.distance_to(button.position)
                if dist < 50 and abs(cube.position.z - button.position.z) < 30:
                    button.pressed = True
                    cube.on_button_id = button.id
                    break

        # Check door states
        # If button pressed, door should be open (if connected)
        for door in model.doors.values():
            # Check if any controlling button is pressed
            for button in model.buttons.values():
                if door.id in button.connected_door_ids and button.pressed:
                    door.open = True
                    door.door_state = 2

        return model

    def _build_rooms(self, model: WorldModel) -> Dict[int, Room]:
        """
        Build rooms from surfaces and entities
        Simplified: group surfaces by proximity and create rooms
        """
        rooms = {}
        if not model.surfaces:
            # Create single room containing all entities
            # Calculate bounds from entities
            if model.entities:
                all_pos = [e.position for e in model.entities.values()]
                min_x = min(p.x for p in all_pos) - 100
                min_y = min(p.y for p in all_pos) - 100
                min_z = min(p.z for p in all_pos) - 50
                max_x = max(p.x for p in all_pos) + 100
                max_y = max(p.y for p in all_pos) + 100
                max_z = max(p.z for p in all_pos) + 200
                bounds = Bounds(Vector3(min_x, min_y, min_z), Vector3(max_x, max_y, max_z))
            else:
                bounds = Bounds(Vector3(-512,-512,0), Vector3(512,512,256))

            room = Room(
                id=0,
                bounds=bounds,
                surfaces=list(model.surfaces.keys()),
                entity_ids=list(model.entities.keys()),
                floor_z=bounds.mins.z,
                ceiling_z=bounds.maxs.z
            )
            rooms[0] = room
            return rooms

        # More advanced: cluster surfaces into rooms based on connectivity
        # For now, single room
        all_surface_ids = list(model.surfaces.keys())
        # Compute overall bounds
        if model.surfaces:
            mins = Vector3(float('inf'), float('inf'), float('inf'))
            maxs = Vector3(float('-inf'), float('-inf'), float('-inf'))
            for surf in model.surfaces.values():
                mins.x = min(mins.x, surf.bounds.mins.x)
                mins.y = min(mins.y, surf.bounds.mins.y)
                mins.z = min(mins.z, surf.bounds.mins.z)
                maxs.x = max(maxs.x, surf.bounds.maxs.x)
                maxs.y = max(maxs.y, surf.bounds.maxs.y)
                maxs.z = max(maxs.z, surf.bounds.maxs.z)
            bounds = Bounds(mins, maxs)
        else:
            bounds = Bounds(Vector3(-512,-512,0), Vector3(512,512,256))

        room = Room(
            id=0,
            bounds=bounds,
            surfaces=all_surface_ids,
            entity_ids=list(model.entities.keys()),
            floor_z=bounds.mins.z,
            ceiling_z=bounds.maxs.z
        )
        rooms[0] = room

        # If we have doors, split into rooms on each side of door
        # Simplified: if door exists, create second room beyond door
        if model.doors:
            for door in model.doors.values():
                # Create room beyond door (north of door)
                beyond_bounds = Bounds(
                    Vector3(door.position.x - 100, door.position.y, door.position.z),
                    Vector3(door.position.x + 100, door.position.y + 200, door.position.z + 200)
                )
                room2 = Room(
                    id=len(rooms),
                    bounds=beyond_bounds,
                    surfaces=[],
                    entity_ids=[eid for eid, ent in model.entities.items() if ent.position.y > door.position.y],
                    connections=[0],
                    floor_z=beyond_bounds.mins.z,
                    ceiling_z=beyond_bounds.maxs.z
                )
                rooms[room2.id] = room2
                # Connect
                rooms[0].connections.append(room2.id)

        return rooms

    def _determine_goals(self, model: WorldModel) -> List[Goal]:
        goals = []
        # Exit is primary goal
        for exit_door in model.exits.values():
            goals.append(Goal(
                type="reach_exit",
                target_id=exit_door.id,
                target_position=exit_door.position,
                description=f"Reach exit at {exit_door.position}",
                priority=100
            ))

        # Buttons as secondary goals if they control doors
        for button in model.buttons.values():
            if not button.pressed:
                goals.append(Goal(
                    type="activate_button",
                    target_id=button.id,
                    target_position=button.position,
                    description=f"Activate button {button.id}",
                    priority=80
                ))

        # Cubes as goals if needed for buttons
        for cube in model.cubes.values():
            # If cube not on button and button needs it
            if cube.on_button_id is None:
                # Check if any unpressed button nearby
                for button in model.buttons.values():
                    if not button.pressed and button.position.distance_to(cube.position) < 1000:
                        goals.append(Goal(
                            type="get_cube",
                            target_id=cube.id,
                            target_position=cube.position,
                            description=f"Get cube {cube.id} for button {button.id}",
                            priority=70
                        ))
                        break

        # Sort by priority
        goals.sort(key=lambda g: g.priority, reverse=True)
        return goals

    def _build_connections(self, model: WorldModel) -> Dict[int, any]:
        # Connections already built in rooms, but also door connections
        from ..world_model.model import Connection
        connections = {}
        conn_id = 0
        for room in model.rooms.values():
            for connected_room_id in room.connections:
                # Find door between rooms if exists
                door_id = None
                for door in model.doors.values():
                    # Check if door is between these rooms (simplified)
                    if door.position.distance_to(room.bounds.center()) < 500:
                        door_id = door.id
                        break

                conn = Connection(
                    id=conn_id,
                    from_room_id=room.id,
                    to_room_id=connected_room_id,
                    type="door" if door_id else "corridor",
                    position=room.bounds.center(),
                    required_entity_id=door_id,
                    traversable=True if not door_id else model.doors.get(door_id, {}).open if hasattr(model.doors.get(door_id), 'open') else False
                )
                connections[conn_id] = conn
                conn_id += 1

        return connections
