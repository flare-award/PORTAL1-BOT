"""
Object Relationships - stores relations between objects:
Button requires Cube
Door controlled_by Button
Exit behind Door
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from enum import Enum

class RelationType(Enum):
    REQUIRES = "requires"  # Button requires Cube
    CONTROLLED_BY = "controlled_by"  # Door controlled_by Button
    BEHIND = "behind"  # Exit behind Door
    BLOCKS = "blocks"  # Door blocks path
    POWERS = "powers"  # Button powers Door
    HOLDS = "holds"  # Button holds Cube?
    CONNECTED_TO = "connected_to"  # Portal connected to surface

@dataclass
class Relationship:
    source_id: int
    target_id: int
    relation_type: RelationType
    metadata: Dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "source": self.source_id,
            "target": self.target_id,
            "type": self.relation_type.value,
            "metadata": self.metadata
        }

class RelationshipGraph:
    def __init__(self):
        self.relationships: List[Relationship] = []
        self.by_source: Dict[int, List[Relationship]] = {}
        self.by_target: Dict[int, List[Relationship]] = {}

    def add_relationship(self, source_id: int, target_id: int, relation_type: RelationType, metadata: Dict = None):
        rel = Relationship(source_id, target_id, relation_type, metadata or {})
        self.relationships.append(rel)
        self.by_source.setdefault(source_id, []).append(rel)
        self.by_target.setdefault(target_id, []).append(rel)
        return rel

    def get_relationships_from(self, source_id: int) -> List[Relationship]:
        return self.by_source.get(source_id, [])

    def get_relationships_to(self, target_id: int) -> List[Relationship]:
        return self.by_target.get(target_id, [])

    def get_dependencies(self, entity_id: int) -> List[int]:
        """
        Get all entities that this entity depends on (requires, controlled_by, behind)
        For example, Door depends on Button, Button depends on Cube
        """
        dependencies = []
        # Find relationships where entity is source and type is REQUIRES, BEHIND, CONTROLLED_BY, BLOCKS
        for rel in self.get_relationships_from(entity_id):
            if rel.relation_type in [RelationType.REQUIRES, RelationType.BEHIND, RelationType.CONTROLLED_BY, RelationType.BLOCKS]:
                dependencies.append(rel.target_id)
        # Also check inverse: if something controls this, that something is dependency?
        # Actually Door controlled_by Button means Door requires Button
        # So we already have Door -> Button as CONTROLLED_BY
        # But also Button REQUIRES Cube
        return dependencies

    def get_dependents(self, entity_id: int) -> List[int]:
        """
        Get entities that depend on this entity
        """
        dependents = []
        for rel in self.get_relationships_to(entity_id):
            if rel.relation_type in [RelationType.REQUIRES, RelationType.BEHIND, RelationType.CONTROLLED_BY, RelationType.BLOCKS]:
                dependents.append(rel.source_id)
        return dependents

    def resolve_dependency_order(self, goal_id: int) -> List[int]:
        """
        Given a goal entity id (e.g., exit), resolve order of entities to activate
        Returns list of entity ids in order they need to be handled (dependencies first)
        Example: Exit behind Door, Door controlled_by Button, Button requires Cube
        -> [Cube, Button, Door, Exit]
        """
        visited = set()
        order = []

        def dfs(entity_id: int):
            if entity_id in visited:
                return
            visited.add(entity_id)
            for dep_id in self.get_dependencies(entity_id):
                dfs(dep_id)
            order.append(entity_id)

        dfs(goal_id)
        return order

    def build_from_world_model(self, world_model):
        """
        Auto-build relationships from WorldModel based on:
        - Button.connected_door_ids
        - Door.connected_button_ids
        - Exit.behind_door_id
        - Entity properties (I/O connections from BSP)
        """
        self.relationships.clear()
        self.by_source.clear()
        self.by_target.clear()

        # From buttons
        for button in world_model.buttons.values():
            for door_id in button.connected_door_ids:
                # Button powers door, door controlled_by button
                self.add_relationship(door_id, button.id, RelationType.CONTROLLED_BY)
                self.add_relationship(button.id, door_id, RelationType.POWERS)
                # Door blocks path, but requires button
                self.add_relationship(door_id, button.id, RelationType.REQUIRES)

        # From doors
        for door in world_model.doors.values():
            for button_id in door.connected_button_ids:
                # Avoid duplicate if already added
                exists = any(r.source_id == door.id and r.target_id == button_id and r.relation_type == RelationType.CONTROLLED_BY for r in self.relationships)
                if not exists:
                    self.add_relationship(door.id, button_id, RelationType.CONTROLLED_BY)
                    self.add_relationship(door.id, button_id, RelationType.REQUIRES)

        # From exits
        for exit_door in world_model.exits.values():
            if exit_door.behind_door_id:
                self.add_relationship(exit_door.id, exit_door.behind_door_id, RelationType.BEHIND)
                self.add_relationship(exit_door.id, exit_door.behind_door_id, RelationType.REQUIRES)

        # From BSP I/O connections (if available in entity properties)
        for ent in world_model.entities.values():
            # Check for connections like "OnPressed -> door.Open"
            # In BSP entities lump, there might be properties like "connections" or specific outputs
            # For this implementation, we parse if properties contain "OnPressed" etc.
            props = ent.properties
            if isinstance(props, dict):
                # Look for keys that start with On*
                for key, value in props.items():
                    if key.startswith("On"):
                        # value is like "door_1,Open,0,0,-1"
                        # Parse target
                        parts = value.split(',')
                        if len(parts) >= 2:
                            target_name = parts[0]
                            action = parts[1]
                            # Find entity by targetname
                            # In Portal 1, entities have targetname
                            # Search for entity with that targetname
                            target_ent = None
                            for other in world_model.entities.values():
                                if other.properties.get("targetname") == target_name:
                                    target_ent = other
                                    break
                            if target_ent:
                                # Infer relationship
                                if "Pressed" in key and "Open" in action:
                                    self.add_relationship(target_ent.id, ent.id, RelationType.CONTROLLED_BY)
                                    self.add_relationship(target_ent.id, ent.id, RelationType.REQUIRES)

        # Heuristic: Button requires Cube if cube is nearest
        for button in world_model.buttons.values():
            if not button.connected_door_ids:
                continue
            # Find nearest cube
            nearest_cube = world_model.get_nearest_cube(button.position)
            if nearest_cube:
                # Check if already has requirement
                has_cube_req = any(r.source_id == button.id and r.target_id == nearest_cube.id for r in self.relationships)
                if not has_cube_req:
                    self.add_relationship(button.id, nearest_cube.id, RelationType.REQUIRES, {"object_type": "cube"})

        print(f"[RelationshipGraph] Built {len(self.relationships)} relationships")

    def to_dict(self):
        return {
            "relationships": [r.to_dict() for r in self.relationships]
        }

    def summary(self) -> str:
        lines = [f"RelationshipGraph: {len(self.relationships)} relationships"]
        for rel in self.relationships:
            lines.append(f"  {rel.source_id} --{rel.relation_type.value}--> {rel.target_id}")
        return "\n".join(lines)
