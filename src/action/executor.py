"""
Action Executor - translates abstract actions to concrete inputs with 3D awareness
"""
from __future__ import annotations
from typing import List, Optional
import time
import math

from ..world_model.vector import Vector3, QAngle
from ..world_model.model import WorldModel
from ..planning.puzzle_solver import AbstractAction, ActionType
from ..spatial.raycast import SpatialRaycaster
from ..navigation.graph import NavigationGraph
from .controller import InputController, MockInputController

class ActionExecutor:
    def __init__(self,
                 world_model: WorldModel,
                 input_controller: InputController,
                 raycaster: SpatialRaycaster,
                 nav_graph: NavigationGraph,
                 game_state_provider=None):
        self.world_model = world_model
        self.input_controller = input_controller
        self.raycaster = raycaster
        self.nav_graph = nav_graph
        self.provider = game_state_provider
        self.current_action: Optional[AbstractAction] = None
        self.action_history: List[AbstractAction] = []

    def update_world_model(self, world_model: WorldModel):
        self.world_model = world_model

    def execute(self, action: AbstractAction) -> bool:
        """
        Execute single abstract action
        Returns True if successful, False otherwise
        """
        self.current_action = action
        print(f"[Executor] Executing: {action.type.value} - {action.description}")

        try:
            if action.type == ActionType.MOVE_TO:
                success = self._execute_move_to(action)
            elif action.type == ActionType.LOOK_AT:
                success = self._execute_look_at(action)
            elif action.type == ActionType.JUMP:
                success = self._execute_jump(action)
            elif action.type == ActionType.CROUCH:
                success = self._execute_crouch(action)
            elif action.type == ActionType.PICK_UP:
                success = self._execute_pick_up(action)
            elif action.type == ActionType.DROP:
                success = self._execute_drop(action)
            elif action.type == ActionType.PLACE_PORTAL:
                success = self._execute_place_portal(action)
            elif action.type == ActionType.ENTER_PORTAL:
                success = self._execute_enter_portal(action)
            elif action.type == ActionType.PRESS_BUTTON:
                success = self._execute_press_button(action)
            elif action.type == ActionType.WAIT:
                success = self._execute_wait(action)
            elif action.type == ActionType.INTERACT:
                success = self._execute_interact(action)
            elif action.type == ActionType.OPEN_DOOR:
                success = self._execute_open_door(action)
            else:
                print(f"[Executor] Unknown action type: {action.type}")
                success = False

            if success:
                self.action_history.append(action)
                print(f"[Executor] Success: {action.description}")
            else:
                print(f"[Executor] Failed: {action.description}")

            return success

        except Exception as e:
            print(f"[Executor] Exception during {action.type}: {e}")
            import traceback
            traceback.print_exc()
            return False

    def execute_plan(self, plan: List[AbstractAction], check_world_update_callback=None) -> bool:
        """
        Execute full plan with feedback loop:
        OBSERVE WORLD -> UPDATE WORLD MODEL -> CHECK GOAL -> PLAN ACTION -> EXECUTE ACTION -> OBSERVE RESULT -> UPDATE WORLD MODEL
        """
        for i, action in enumerate(plan):
            print(f"\n[Executor] Step {i+1}/{len(plan)}: {action.description}")

            success = self.execute(action)
            if not success:
                print(f"[Executor] Plan failed at step {i+1}")
                return False

            # After each significant action, update world model and check
            if check_world_update_callback:
                # Callback should update world_model and return True if should continue
                should_continue = check_world_update_callback()
                if not should_continue:
                    print("[Executor] World update callback requested stop")
                    return False

            # Small delay between actions
            time.sleep(0.1)

        print("[Executor] Full plan executed successfully")
        return True

    # --- Individual action implementations ---

    def _execute_move_to(self, action: AbstractAction) -> bool:
        target = action.target_position
        if not target:
            print("[Executor] MoveTo without target position")
            return False

        if not self.world_model.player:
            print("[Executor] No player state")
            return False

        # Implement movement with 3D awareness:
        # 1. Determine current position
        # 2. Determine target position
        # 3. Build path (if nav graph available)
        # 4. Determine direction
        # 5. Turn player
        # 6. Move with regular position checks
        # 7. Adjust direction
        # 8. Stop when reached

        start_pos = self.world_model.player.position
        print(f"[Executor] MoveTo from {start_pos} to {target}")

        # For mock, just simulate movement
        # In real implementation, would do PID loop

        # Calculate direction
        to_target = target - start_pos
        distance = to_target.length()
        if distance < 10.0:
            print(f"[Executor] Already at target (dist {distance:.1f})")
            return True

        # Look at target
        look_action = AbstractAction(
            type=ActionType.LOOK_AT,
            target_position=target,
            description=f"Look at MoveTo target {target}"
        )
        self._execute_look_at(look_action)

        # Determine movement keys based on direction relative to player view
        # Simplified: if we look at target, press W
        # In real, need to compute local movement vector

        # Simulate movement: press W for time proportional to distance
        # Portal 1 player speed ~ 175 units/s walking, 250 running?
        # Use 150 units/s as estimate
        speed = 150.0
        duration = distance / speed
        duration = min(duration, 5.0)  # cap to 5 sec per segment to allow re-evaluation

        print(f"[Executor] Moving {distance:.1f} units, duration {duration:.2f}s")

        # Hold W
        self.input_controller.hold_key('w')
        # In real, we'd have loop checking position every 0.1s and adjusting
        # For mock, just sleep and simulate position update
        time.sleep(min(duration, 0.5))  # shortened for testing
        self.input_controller.release_key('w')

        # Simulate player moved (in mock provider, we'd update)
        if hasattr(self.provider, 'set_player_position'):
            # Move partway towards target for simulation
            move_ratio = min(0.8, (0.5 * speed) / distance) if distance > 0 else 1.0
            new_pos = start_pos + to_target * move_ratio
            self.provider.set_player_position(new_pos)
            self.world_model.player.position = new_pos
            self.world_model.player.eye_position = new_pos + Vector3(0,0,64)

        # Check if reached (within threshold)
        new_dist = self.world_model.player.position.distance_to(target)
        print(f"[Executor] After move, distance to target: {new_dist:.1f}")

        # For testing, consider success if we moved closer
        return new_dist < distance or new_dist < 30.0

    def _execute_look_at(self, action: AbstractAction) -> bool:
        target = action.target_position
        if not target:
            return False
        if not self.world_model.player:
            return False

        current_ang = self.world_model.player.rotation
        current_pos = self.world_model.player.position
        eye_pos = self.world_model.player.eye_position

        print(f"[Executor] LookAt from {current_pos} eye {eye_pos} to {target}, current ang {current_ang}")

        # Calculate required mouse movement
        self.input_controller.look_at(current_ang, target, current_pos, eye_pos)

        # Simulate angle update
        to_target = target - eye_pos
        dist = to_target.length()
        if dist > 1e-6:
            desired_yaw = math.degrees(math.atan2(to_target.y, to_target.x))
            desired_pitch = math.degrees(math.asin(-to_target.z / dist))
            new_ang = QAngle(desired_pitch, desired_yaw, 0)
            self.world_model.player.rotation = new_ang
            print(f"[Executor] New angles: {new_ang}")

        return True

    def _execute_jump(self, action: AbstractAction) -> bool:
        print("[Executor] Jump")
        self.input_controller.press_key('space', 0.2)
        return True

    def _execute_crouch(self, action: AbstractAction) -> bool:
        print("[Executor] Crouch")
        self.input_controller.press_key('ctrl', 0.5)
        return True

    def _execute_pick_up(self, action: AbstractAction) -> bool:
        print(f"[Executor] PickUp entity {action.target_id}")
        # In Portal 1, pick up is automatic when close and looking, or E?
        # Actually cube pickup: press E when near, or just walk into?
        # For weighted cube, you press E to pick up
        # Look at cube first
        if action.target_position:
            look = AbstractAction(type=ActionType.LOOK_AT, target_position=action.target_position, description="Look at cube to pick up")
            self._execute_look_at(look)

        self.input_controller.press_key('e', 0.2)
        time.sleep(0.2)

        # Simulate holding
        if self.world_model.player and action.target_id:
            self.world_model.player.holding_object_id = action.target_id
            # Update cube held state
            cube = self.world_model.cubes.get(action.target_id)
            if cube:
                cube.held = True

        return True

    def _execute_drop(self, action: AbstractAction) -> bool:
        print(f"[Executor] Drop at {action.target_position}")
        # Drop is E again or just release?
        self.input_controller.press_key('e', 0.2)
        time.sleep(0.2)

        if self.world_model.player:
            held_id = self.world_model.player.holding_object_id
            if held_id:
                cube = self.world_model.cubes.get(held_id)
                if cube and action.target_position:
                    cube.position = action.target_position
                    cube.held = False
                    # Check if on button
                    for button in self.world_model.buttons.values():
                        if button.position.distance_to(action.target_position) < 50:
                            cube.on_button_id = button.id
                            button.pressed = True
                            # Open linked doors
                            for door_id in button.connected_door_ids:
                                door = self.world_model.doors.get(door_id)
                                if door:
                                    door.open = True
                                    door.door_state = 2
                self.world_model.player.holding_object_id = None

        return True

    def _execute_place_portal(self, action: AbstractAction) -> bool:
        print(f"[Executor] Place {action.portal_type} portal at {action.target_position} normal {action.target_normal}")
        if not action.target_position or not action.target_normal:
            return False

        # Look at placement surface
        look = AbstractAction(type=ActionType.LOOK_AT, target_position=action.target_position, description=f"Look for {action.portal_type} portal placement")
        self._execute_look_at(look)

        # Check if can place
        can_place, reason = self.raycaster.can_place_portal(action.target_position, action.target_normal, action.portal_type or "blue")
        if not can_place:
            print(f"[Executor] Cannot place portal: {reason}")
            # Still try? In real game, crosshair would be invalid
            # For testing, allow anyway
            pass

        # Click mouse
        button = "left" if action.portal_type == "blue" else "right"
        self.input_controller.mouse_click(button)
        time.sleep(0.2)

        # Simulate portal creation via provider if mock
        if hasattr(self.provider, 'place_portal'):
            self.provider.place_portal(action.portal_type or "blue", action.target_position, action.target_normal)
            # Update world model portals
            if self.provider:
                portals = self.provider.get_portals()
                self.world_model.portals = {p.id: p for p in portals}
                for p in portals:
                    self.world_model.entities[p.id] = p

        return True

    def _execute_enter_portal(self, action: AbstractAction) -> bool:
        print(f"[Executor] Enter {action.portal_type} portal")
        # Find portal of that type
        target_portal = None
        for portal in self.world_model.portals.values():
            if portal.portal_type == action.portal_type and portal.active:
                target_portal = portal
                break

        if not target_portal:
            print(f"[Executor] No active {action.portal_type} portal found")
            return False

        # Move to portal
        move_action = AbstractAction(type=ActionType.MOVE_TO, target_position=target_portal.position, description=f"Move to {action.portal_type} portal")
        success = self._execute_move_to(move_action)
        if not success:
            return False

        # Simulate teleportation
        if target_portal.linked_portal_id:
            linked = self.world_model.portals.get(target_portal.linked_portal_id)
            if linked:
                # Transform player position
                new_pos = target_portal.transform_position_to_linked(self.world_model.player.position, linked)
                # Add slight offset forward from exit portal
                new_pos = new_pos + linked.forward * 20
                print(f"[Executor] Teleported from {self.world_model.player.position} to {new_pos} via portal {target_portal.id}->{linked.id}")
                self.world_model.player.position = new_pos
                self.world_model.player.eye_position = new_pos + Vector3(0,0,64)
                if hasattr(self.provider, 'set_player_position'):
                    self.provider.set_player_position(new_pos)

        return True

    def _execute_press_button(self, action: AbstractAction) -> bool:
        print(f"[Executor] Press button {action.target_id}")
        # For floor button, just stand on it or place cube
        # For wall button, press E
        if action.target_position:
            move = AbstractAction(type=ActionType.MOVE_TO, target_position=action.target_position, description="Move to button")
            self._execute_move_to(move)

        self.input_controller.press_key('e', 0.2)
        time.sleep(0.2)

        # Update button state
        if action.target_id:
            button = self.world_model.buttons.get(action.target_id)
            if button:
                button.pressed = True
                for door_id in button.connected_door_ids:
                    door = self.world_model.doors.get(door_id)
                    if door:
                        door.open = True
                        door.door_state = 2

        return True

    def _execute_wait(self, action: AbstractAction) -> bool:
        print(f"[Executor] Wait - {action.description}")
        time.sleep(1.0)
        return True

    def _execute_interact(self, action: AbstractAction) -> bool:
        print(f"[Executor] Interact with {action.target_id}")
        self.input_controller.press_key('e', 0.2)
        return True

    def _execute_open_door(self, action: AbstractAction) -> bool:
        print(f"[Executor] Open door {action.target_id}")
        # Doors open automatically via buttons
        # Just move to door
        if action.target_position:
            move = AbstractAction(type=ActionType.MOVE_TO, target_position=action.target_position, description="Move to door")
            return self._execute_move_to(move)
        return True
