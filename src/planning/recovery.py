"""
Recovery system - detects failures and recovers
Detects:
- Stuck (position not changing)
- Cannot pass
- Wrong portal
- Wrong trajectory
- Death
- Lost object
- Cannot perform action
"""
from __future__ import annotations
from typing import List, Optional, Dict
import time
from collections import deque

from ..world_model.vector import Vector3
from ..world_model.model import WorldModel
from ..planning.puzzle_solver import AbstractAction

class RecoverySystem:
    def __init__(self, world_model: WorldModel):
        self.world_model = world_model
        self.position_history: deque = deque(maxlen=50)  # last 50 positions with timestamps
        self.action_failures: Dict[str, int] = {}  # action type -> failure count
        self.last_progress_time = time.time()
        self.stuck_threshold = 5.0  # seconds without movement considered stuck
        self.min_movement = 10.0  # minimum movement to not be stuck

    def update(self, world_model: WorldModel):
        self.world_model = world_model
        if world_model.player:
            self.position_history.append((world_model.player.position, time.time()))

    def is_stuck(self) -> bool:
        if len(self.position_history) < 10:
            return False
        # Check if positions in last N seconds have not changed much
        recent_positions = [pos for pos, t in self.position_history if time.time() - t < self.stuck_threshold]
        if len(recent_positions) < 2:
            return False
        # Compute max distance from first to any recent
        first = recent_positions[0]
        max_dist = max(first.distance_to(p) for p in recent_positions)
        return max_dist < self.min_movement

    def is_dead(self) -> bool:
        if self.world_model.player:
            return not self.world_model.player.alive
        return False

    def is_cube_lost(self, expected_cube_id: int, expected_position: Vector3) -> bool:
        cube = self.world_model.cubes.get(expected_cube_id)
        if not cube:
            return True
        # If cube far from expected and not held
        if cube.held:
            return False
        dist = cube.position.distance_to(expected_position)
        return dist > 200  # lost if far

    def is_portal_wrong(self) -> bool:
        # Check if portals are placed but not useful
        # For example, both portals on same wall, or portal leads to void
        # Simplified: if we have portals but path still not found to goal
        active_portals = [p for p in self.world_model.portals.values() if p.active]
        if len(active_portals) == 2:
            blue = next((p for p in active_portals if p.portal_type == "blue"), None)
            orange = next((p for p in active_portals if p.portal_type == "orange"), None)
            if blue and orange:
                # Check if portals are too close (same surface)
                if blue.position.distance_to(orange.position) < 100:
                    # Likely wrong, same area
                    return True
                # Check if linked
                if blue.linked_portal_id != orange.id and orange.linked_portal_id != blue.id:
                    return True
        return False

    def detect_failure(self, action: AbstractAction) -> Optional[str]:
        """
        Detect failure reason for last action
        Returns failure reason string or None if no failure
        """
        if self.is_dead():
            return "player_died"

        if self.is_stuck():
            return "stuck"

        if self.is_portal_wrong():
            return "wrong_portal"

        # Check action-specific failures
        if action.type.value == "move_to":
            # If we tried to move but position didn't change much
            if len(self.position_history) >= 2:
                last_pos, _ = self.position_history[-1]
                prev_pos, _ = self.position_history[-2]
                if last_pos.distance_to(prev_pos) < 5.0:
                    # Check if target was far
                    if action.target_position and last_pos.distance_to(action.target_position) > 50:
                        return "cannot_reach_target"

        if action.type.value == "pick_up":
            # Check if cube still not held
            if self.world_model.player and self.world_model.player.holding_object_id != action.target_id:
                return "failed_to_pick_up"

        if action.type.value == "place_portal":
            # Check if portal active after placement
            if action.portal_type:
                portal = next((p for p in self.world_model.portals.values() if p.portal_type == action.portal_type and p.active), None)
                if not portal:
                    return "portal_placement_failed"

        return None

    def get_recovery_action(self, failure_reason: str) -> Optional[AbstractAction]:
        """
        Suggest recovery action based on failure
        """
        from ..planning.puzzle_solver import AbstractAction, ActionType

        if failure_reason == "stuck":
            # Try to jump and move randomly
            return AbstractAction(
                type=ActionType.JUMP,
                description="Recovery: Jump to get unstuck"
            )

        elif failure_reason == "player_died":
            # Wait for respawn
            return AbstractAction(
                type=ActionType.WAIT,
                description="Recovery: Wait for respawn after death"
            )

        elif failure_reason == "wrong_portal":
            # Remove portals and try again? In Portal 1, placing new portal overwrites
            # So suggest placing portals elsewhere
            return AbstractAction(
                type=ActionType.PLACE_PORTAL,
                portal_type="blue",
                description="Recovery: Replace wrong portal"
            )

        elif failure_reason == "cannot_reach_target":
            # Try alternative path or portal
            return AbstractAction(
                type=ActionType.PLACE_PORTAL,
                description="Recovery: Place portal to reach target"
            )

        elif failure_reason == "failed_to_pick_up":
            # Try looking again and pressing E
            return AbstractAction(
                type=ActionType.LOOK_AT,
                description="Recovery: Look at cube again for pickup"
            )

        elif failure_reason == "portal_placement_failed":
            # Try different surface
            return AbstractAction(
                type=ActionType.LOOK_AT,
                description="Recovery: Look for alternative portal surface"
            )

        return None

    def should_replan(self, failure_reason: str) -> bool:
        """
        Determine if we should replan from scratch
        """
        return failure_reason in ["stuck", "player_died", "wrong_portal", "cannot_reach_target"]

    def reset(self):
        self.position_history.clear()
        self.action_failures.clear()
        self.last_progress_time = time.time()
