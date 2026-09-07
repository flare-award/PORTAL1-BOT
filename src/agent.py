"""
Full Portal Agent - main loop
ARCHITECTURE:
OBSERVE WORLD -> UPDATE WORLD MODEL -> CHECK GOAL -> PLAN ACTION -> EXECUTE ACTION -> OBSERVE RESULT -> UPDATE WORLD MODEL
"""
from __future__ import annotations
from typing import Optional, List
import time

from .game_state.provider import GameStateProvider
from .game_state.implementations.aggregated_provider import AggregatedProvider
from .game_state.implementations.mock_provider import MockProvider
from .world_model.model import WorldModel, Goal
from .spatial.raycast import SpatialRaycaster
from .spatial.queries import SpatialQuerySystem
from .navigation.builder import NavigationGraphBuilder
from .navigation.graph import NavigationGraph
from .planning.object_relationships import RelationshipGraph
from .planning.goal_planner import GoalPlanner
from .planning.puzzle_solver import ActionPlanner, AbstractAction
from .planning.recovery import RecoverySystem
from .action.executor import ActionExecutor
from .action.controller import InputController, MockInputController
from .perception.interpretation import WorldInterpreter

class PortalAgent:
    def __init__(self,
                 provider: GameStateProvider,
                 input_controller: Optional[InputController] = None,
                 debug: bool = True):

        self.provider = provider
        self.input_controller = input_controller or MockInputController()
        self.debug = debug

        # Core systems
        self.world_model: Optional[WorldModel] = None
        self.raycaster = SpatialRaycaster(provider)
        self.spatial_queries: Optional[SpatialQuerySystem] = None
        self.nav_graph: Optional[NavigationGraph] = None
        self.relationship_graph = RelationshipGraph()
        self.goal_planner: Optional[GoalPlanner] = None
        self.action_planner: Optional[ActionPlanner] = None
        self.executor: Optional[ActionExecutor] = None
        self.recovery = None
        self.interpreter = WorldInterpreter(provider)

        # State
        self.current_goal: Optional[Goal] = None
        self.current_plan: List[AbstractAction] = []
        self.running = False
        self.iteration = 0

        # Initialize
        self._initialize()

    def _initialize(self):
        print("[Agent] Initializing...")
        # Initial world model
        self.world_model = self.interpreter.interpret()
        self.spatial_queries = SpatialQuerySystem(self.world_model, self.raycaster)

        # Build navigation graph
        builder = NavigationGraphBuilder(self.world_model, self.raycaster)
        self.nav_graph = builder.build()

        # Build relationships
        self.relationship_graph.build_from_world_model(self.world_model)

        # Planners
        self.goal_planner = GoalPlanner(self.world_model, self.relationship_graph)
        self.action_planner = ActionPlanner(
            self.world_model,
            self.spatial_queries,
            self.nav_graph,
            self.relationship_graph,
            self.raycaster
        )

        # Executor
        self.executor = ActionExecutor(
            self.world_model,
            self.input_controller,
            self.raycaster,
            self.nav_graph,
            self.provider
        )

        # Recovery
        self.recovery = RecoverySystem(self.world_model)

        print("[Agent] Initialized")
        print(self.world_model.summary())
        print(self.relationship_graph.summary())
        print(self.nav_graph.summary())

    def observe_world(self) -> WorldModel:
        """
        OBSERVE WORLD step
        """
        if self.debug:
            print(f"\n[Agent] Iteration {self.iteration} - OBSERVE WORLD")
        # Get fresh world model from provider via interpreter
        self.world_model = self.interpreter.interpret()

        # Update all systems
        self.spatial_queries.update_world_model(self.world_model)
        self.recovery.update(self.world_model)
        if self.goal_planner:
            self.goal_planner.update_world_model(self.world_model)
        if self.action_planner:
            self.action_planner.update_world_model(self.world_model)
        if self.executor:
            self.executor.update_world_model(self.world_model)

        # Rebuild nav graph if portals changed
        if self.nav_graph:
            builder = NavigationGraphBuilder(self.world_model, self.raycaster)
            # For efficiency, only update portal edges
            self.nav_graph = builder.update_with_portals(self.nav_graph, list(self.world_model.portals.values()))

        return self.world_model

    def check_goal(self) -> Optional[Goal]:
        """
        CHECK GOAL step
        """
        if self.debug:
            print("[Agent] CHECK GOAL")
        self.current_goal = self.goal_planner.get_current_goal()
        if self.current_goal:
            print(f"[Agent] Current goal: {self.current_goal.type} - {self.current_goal.description} (priority {self.current_goal.priority})")
        return self.current_goal

    def plan_action(self) -> List[AbstractAction]:
        """
        PLAN ACTION step
        """
        if self.debug:
            print("[Agent] PLAN ACTION")
        if not self.current_goal:
            print("[Agent] No goal, cannot plan")
            return []

        # Get goal chain (dependencies)
        goal_chain = self.goal_planner.get_goal_chain(self.current_goal)
        print(f"[Agent] Goal chain: {[g.type + ':' + g.description for g in goal_chain]}")

        # Plan for first uncompleted goal in chain
        for goal in goal_chain:
            # Check if goal already completed
            if self._is_goal_completed(goal):
                print(f"[Agent] Goal already completed: {goal.description}")
                continue
            plan = self.action_planner.plan(goal)
            if plan:
                self.current_plan = plan
                print(f"[Agent] Plan for {goal.type}: {len(plan)} actions")
                for i, action in enumerate(plan):
                    print(f"  {i+1}. {action.type.value} - {action.description}")
                return plan

        # If all goals in chain completed, plan for current goal directly
        plan = self.action_planner.plan(self.current_goal)
        self.current_plan = plan
        print(f"[Agent] Direct plan: {len(plan)} actions")
        for i, action in enumerate(plan):
            print(f"  {i+1}. {action.type.value} - {action.description}")
        return plan

    def _is_goal_completed(self, goal: Goal) -> bool:
        if goal.type == "reach_exit":
            if self.world_model.player and goal.target_position:
                return self.world_model.player.position.distance_to(goal.target_position) < 100
        elif goal.type == "activate_button":
            button = self.world_model.buttons.get(goal.target_id) if goal.target_id else None
            if button:
                return button.pressed
        elif goal.type == "get_cube":
            # Completed if holding cube or cube on button?
            if self.world_model.player and self.world_model.player.holding_object_id == goal.target_id:
                return True
            # Or if cube is on its target button?
            cube = self.world_model.cubes.get(goal.target_id) if goal.target_id else None
            if cube and cube.on_button_id:
                return True
        elif goal.type == "open_door":
            door = self.world_model.doors.get(goal.target_id) if goal.target_id else None
            if door:
                return door.open
        return False

    def execute_action(self) -> bool:
        """
        EXECUTE ACTION step with feedback loop
        """
        if self.debug:
            print("[Agent] EXECUTE ACTION")

        if not self.current_plan:
            print("[Agent] No plan to execute")
            return False

        # Execute plan step by step with world updates
        def world_update_callback():
            # Observe world after each action
            self.observe_world()
            # Check for failures
            if self.current_plan:
                last_action = self.executor.current_action
                if last_action:
                    failure = self.recovery.detect_failure(last_action)
                    if failure:
                        print(f"[Agent] Detected failure: {failure}")
                        recovery_action = self.recovery.get_recovery_action(failure)
                        if recovery_action:
                            print(f"[Agent] Attempting recovery: {recovery_action.description}")
                            self.executor.execute(recovery_action)
                        if self.recovery.should_replan(failure):
                            print("[Agent] Failure requires replanning")
                            return False  # Stop execution, replan
            return True

        success = self.executor.execute_plan(self.current_plan, check_world_update_callback=world_update_callback)
        return success

    def run_iteration(self) -> bool:
        """
        Run single iteration of main loop
        Returns True if should continue, False if goal reached or failed
        """
        self.iteration += 1
        print(f"\n{'='*60}")
        print(f"[Agent] Iteration {self.iteration}")
        print(f"{'='*60}")

        # OBSERVE
        self.observe_world()

        # CHECK GOAL
        goal = self.check_goal()
        if not goal:
            print("[Agent] No goal, stopping")
            return False

        if goal.type == "reach_exit" and self._is_goal_completed(goal):
            print("[Agent] Goal reached! Exit achieved!")
            return False

        # PLAN
        plan = self.plan_action()
        if not plan:
            print("[Agent] Failed to create plan")
            # Try recovery?
            return False

        # EXECUTE
        success = self.execute_action()
        if not success:
            print("[Agent] Execution failed, will replan next iteration")
            # Don't stop, try again next iteration

        # Check if goal completed after execution
        self.observe_world()
        if self._is_goal_completed(goal):
            print(f"[Agent] Goal completed after execution: {goal.description}")
            # Continue to next goal

        return True

    def run(self, max_iterations: int = 100):
        """
        Main loop
        """
        self.running = True
        print("[Agent] Starting main loop")

        try:
            for _ in range(max_iterations):
                if not self.running:
                    break
                should_continue = self.run_iteration()
                if not should_continue:
                    print("[Agent] Stopping main loop - goal reached or no more actions")
                    break
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("[Agent] Interrupted by user")
        finally:
            self.running = False
            print("[Agent] Main loop ended")

    def stop(self):
        self.running = False

    def get_debug_info(self) -> dict:
        return {
            "iteration": self.iteration,
            "current_goal": self.current_goal.to_dict() if self.current_goal else None,
            "current_plan": [a.to_dict() for a in self.current_plan],
            "current_action": self.executor.current_action.to_dict() if self.executor and self.executor.current_action else None,
            "player_position": self.world_model.player.position.to_tuple() if self.world_model and self.world_model.player else None,
            "player_rotation": (self.world_model.player.rotation.pitch, self.world_model.player.rotation.yaw, self.world_model.player.rotation.roll) if self.world_model and self.world_model.player else None,
            "world_model": self.world_model.to_dict() if self.world_model else None,
            "nav_graph": self.nav_graph.to_dict() if self.nav_graph else None,
            "relationships": self.relationship_graph.to_dict() if self.relationship_graph else None
        }
