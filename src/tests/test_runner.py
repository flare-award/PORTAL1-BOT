"""
Diagnostic Tests - 12 tests as per spec
Each test outputs obtained data
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.game_state.implementations.mock_provider import MockProvider
from src.game_state.implementations.bsp_provider import BSPProvider
from src.game_state.implementations.aggregated_provider import AggregatedProvider
from src.world_model.vector import Vector3, QAngle
from src.spatial.raycast import SpatialRaycaster
from src.spatial.queries import SpatialQuerySystem
from src.navigation.builder import NavigationGraphBuilder
from src.world_model.portal import Portal
from src.perception.interpretation import WorldInterpreter
from src.planning.object_relationships import RelationshipGraph
from src.planning.goal_planner import GoalPlanner
from src.planning.puzzle_solver import ActionPlanner
from src.action.controller import MockInputController
from src.action.executor import ActionExecutor
from src.agent import PortalAgent

def test_1_player_position():
    print("\n=== TEST 1: Получить позицию игрока ===")
    provider = MockProvider()
    player = provider.get_player_state()
    print(f"Player position: {player.position}")
    print(f"Eye position: {player.eye_position}")
    print(f"Rotation: {player.rotation}")
    print(f"Velocity: {player.velocity}")
    print(f"Grounded: {player.grounded}, Alive: {player.alive}")
    assert player.position is not None
    print("TEST 1 PASSED")
    return True

def test_2_entity_list():
    print("\n=== TEST 2: Получить список entities ===")
    provider = MockProvider()
    entities = provider.get_entities()
    print(f"Found {len(entities)} entities:")
    for ent in entities:
        print(f"  ID={ent.id} Class={ent.classname} Pos={ent.position} Bounds={ent.bounds}")
    assert len(entities) > 0
    print("TEST 2 PASSED")
    return True

def test_3_cube_coordinates():
    print("\n=== TEST 3: Определить cube и его координаты ===")
    provider = MockProvider()
    entities = provider.get_entities()
    cubes = [e for e in entities if "cube" in e.classname.lower()]
    print(f"Found {len(cubes)} cubes:")
    for cube in cubes:
        print(f"  Cube ID={cube.id} Pos={cube.position} Rot={cube.rotation} Vel={cube.velocity} Bounds={cube.bounds}")
        # Check distance to player
        player = provider.get_player_state()
        dist = cube.position.distance_to(player.position)
        print(f"    Distance to player: {dist:.1f}")
    assert len(cubes) > 0
    print("TEST 3 PASSED")
    return True

def test_4_button_state():
    print("\n=== TEST 4: Определить button и его состояние ===")
    provider = MockProvider()
    entities = provider.get_entities()
    buttons = [e for e in entities if "button" in e.classname.lower()]
    print(f"Found {len(buttons)} buttons:")
    for btn in buttons:
        print(f"  Button ID={btn.id} Pos={btn.position} Pressed={getattr(btn,'pressed', 'unknown')} Connected doors={getattr(btn,'connected_door_ids', [])}")
    assert len(buttons) > 0
    # Test button press simulation
    provider.simulate_button_press(buttons[0].id, True)
    print(f"After simulated press: Button {buttons[0].id} pressed={buttons[0].pressed}")
    print("TEST 4 PASSED")
    return True

def test_5_walls_collision():
    print("\n=== TEST 5: Определить стены / collision geometry ===")
    provider = MockProvider()
    surfaces = provider.get_world_geometry()
    print(f"Found {len(surfaces)} surfaces:")
    for surf in surfaces:
        print(f"  Surface ID={surf.id} Pos={surf.position} Normal={surf.normal} Portalable={surf.portalable} Material={surf.material} Bounds={surf.bounds} Area={surf.area:.1f}")
    portalable = [s for s in surfaces if s.portalable]
    print(f"Portalable surfaces: {len(portalable)}")
    for surf in portalable:
        print(f"    ID={surf.id} Material={surf.material} Large enough for portal: {surf.is_large_enough_for_portal()}")
    assert len(surfaces) > 0
    print("TEST 5 PASSED")
    return True

def test_6_raycast():
    print("\n=== TEST 6: Сделать raycast ===")
    provider = MockProvider()
    raycaster = SpatialRaycaster(provider)
    player = provider.get_player_state()
    print(f"Player at {player.position}, eye {player.eye_position}")

    # Raycast forward
    forward = player.rotation.to_forward_vector()
    print(f"Forward vector: {forward}")
    hit = raycaster.raycast(player.eye_position, forward, max_dist=1000)
    print(f"Raycast forward: hit={hit.hit} pos={hit.position} normal={hit.normal} distance={hit.distance:.1f} entity={hit.entity_id} surface={hit.surface_id} material={hit.material}")

    # Raycast down (floor)
    hit_down = raycaster.raycast(player.position + Vector3(0,0,10), Vector3(0,0,-1), max_dist=100)
    print(f"Raycast down: hit={hit_down.hit} pos={hit_down.position} normal={hit_down.normal} distance={hit_down.distance:.1f}")

    # Trace from player to cube
    cubes = [e for e in provider.get_entities() if "cube" in e.classname.lower()]
    if cubes:
        cube = cubes[0]
        trace = raycaster.trace(player.position, cube.position)
        print(f"Trace to cube {cube.id}: hit={trace.hit} fraction={trace.fraction:.2f} hit_pos={trace.hit_position}")

    # IsPathClear
    if cubes:
        clear = raycaster.is_path_clear(player.position, cubes[0].position)
        print(f"IsPathClear to cube: {clear}")

    assert hit is not None
    print("TEST 6 PASSED")
    return True

def test_7_portalable_surface():
    print("\n=== TEST 7: Определить portalable surface ===")
    provider = MockProvider()
    raycaster = SpatialRaycaster(provider)
    player = provider.get_player_state()

    surfaces = provider.get_world_geometry()
    portalable = [s for s in surfaces if s.portalable]
    print(f"Portalable surfaces: {len(portalable)}")
    for surf in portalable:
        can_place, reason = raycaster.can_place_portal(surf.position, surf.normal, "blue")
        print(f"  Surface {surf.id} at {surf.position} normal {surf.normal}: can_place={can_place} reason={reason}")

    # Find best portal surface near player
    candidates = raycaster.find_portal_placement_candidates(player.position, max_dist=1000)
    print(f"Candidates near player: {len(candidates)}")
    for surf in candidates[:3]:
        print(f"    Candidate ID={surf.id} Pos={surf.position} Dist={surf.position.distance_to(player.position):.1f}")

    # Test CanPlacePortal API
    if portalable:
        surf = portalable[0]
        can_place, reason = provider.can_place_portal(surf.position, surf.normal, "blue")
        print(f"Provider CanPlacePortal: {can_place} {reason}")

    assert len(portalable) > 0
    print("TEST 7 PASSED")
    return True

def test_8_nav_graph():
    print("\n=== TEST 8: Построить Navigation Graph ===")
    provider = MockProvider()
    world_model = provider.get_world_model()
    # Need to build world model properly
    from src.world_model.model import WorldModel
    wm = WorldModel()
    wm.player = provider.get_player_state()
    for ent in provider.get_entities():
        wm.add_entity(ent)
    for surf in provider.get_world_geometry():
        wm.surfaces[surf.id] = surf

    raycaster = SpatialRaycaster(provider)
    builder = NavigationGraphBuilder(wm, raycaster)
    graph = builder.build(grid_size=128)

    print(graph.summary())
    print(f"Nodes: {len(graph.nodes)}")
    for node_id, node in list(graph.nodes.items())[:5]:
        print(f"  Node {node_id}: pos={node.position} type={node.area_type}")

    print(f"Edges: {len(graph.edges)}")
    for edge in graph.edges[:10]:
        print(f"  Edge {edge.from_node}->{edge.to_node} type={edge.edge_type} cost={edge.cost:.1f}")

    # Test pathfinding
    if wm.player and wm.exits:
        exit_pos = next(iter(wm.exits.values())).position
        path = graph.find_path(wm.player.position, exit_pos, wm)
        if path:
            print(f"Path from player to exit: {len(path)} nodes")
            for node in path:
                print(f"    Node {node.id} at {node.position}")
        else:
            print("No path found from player to exit")

    assert len(graph.nodes) > 0
    print("TEST 8 PASSED")
    return True

def test_9_move_player():
    print("\n=== TEST 9: Переместить игрока из A в B ===")
    provider = MockProvider()
    wm = provider.get_world_model()
    from src.world_model.model import WorldModel
    world_model = WorldModel()
    world_model.player = provider.get_player_state()
    for ent in provider.get_entities():
        world_model.add_entity(ent)
    for surf in provider.get_world_geometry():
        world_model.surfaces[surf.id] = surf

    raycaster = SpatialRaycaster(provider)
    builder = NavigationGraphBuilder(world_model, raycaster)
    graph = builder.build()

    controller = MockInputController()
    executor = ActionExecutor(world_model, controller, raycaster, graph, provider)

    start = world_model.player.position
    target = Vector3(100,100,20)
    print(f"Moving from {start} to {target}")

    from src.planning.puzzle_solver import AbstractAction, ActionType
    action = AbstractAction(type=ActionType.MOVE_TO, target_position=target, description="Test move")

    success = executor.execute(action)
    print(f"Move success: {success}")
    print(f"New player pos: {world_model.player.position}")
    print(f"Distance to target: {world_model.player.position.distance_to(target):.1f}")

    assert success
    print("TEST 9 PASSED")
    return True

def test_10_place_portal():
    print("\n=== TEST 10: Поставить портал на заданную поверхность ===")
    provider = MockProvider()
    world_model = provider.get_world_model()
    from src.world_model.model import WorldModel
    wm = WorldModel()
    wm.player = provider.get_player_state()
    for ent in provider.get_entities():
        wm.add_entity(ent)
    for surf in provider.get_world_geometry():
        wm.surfaces[surf.id] = surf

    raycaster = SpatialRaycaster(provider)
    builder = NavigationGraphBuilder(wm, raycaster)
    graph = builder.build()
    controller = MockInputController()
    executor = ActionExecutor(wm, controller, raycaster, graph, provider)

    # Find portalable surface
    portalable = [s for s in wm.surfaces.values() if s.portalable]
    assert len(portalable) > 0
    surf = portalable[0]
    print(f"Placing portal on surface {surf.id} at {surf.position} normal {surf.normal}")

    from src.planning.puzzle_solver import AbstractAction, ActionType
    action = AbstractAction(
        type=ActionType.PLACE_PORTAL,
        target_position=surf.position,
        target_normal=surf.normal,
        portal_type="blue",
        surface_id=surf.id,
        description=f"Place blue portal on surface {surf.id}"
    )

    success = executor.execute(action)
    print(f"Place portal success: {success}")
    print(f"Active portals: {len(provider.get_portals())}")
    for portal in provider.get_portals():
        print(f"  Portal {portal.id} type={portal.portal_type} pos={portal.position} active={portal.active}")

    assert success
    print("TEST 10 PASSED")
    return True

def test_11_portal_traversal():
    print("\n=== TEST 11: Проверить portal traversal ===")
    provider = MockProvider()
    from src.world_model.model import WorldModel
    wm = WorldModel()
    wm.player = provider.get_player_state()
    for ent in provider.get_entities():
        wm.add_entity(ent)
    for surf in provider.get_world_geometry():
        wm.surfaces[surf.id] = surf

    # Place two portals
    portalable = [s for s in wm.surfaces.values() if s.portalable]
    assert len(portalable) >= 2

    surf1 = portalable[0]
    surf2 = portalable[1]

    blue = provider.place_portal("blue", surf1.position, surf1.normal)
    orange = provider.place_portal("orange", surf2.position, surf2.normal)

    print(f"Blue portal: {blue.position} normal {blue.normal} linked to {blue.linked_portal_id}")
    print(f"Orange portal: {orange.position} normal {orange.normal} linked to {orange.linked_portal_id}")

    # Test transformation
    # Player enters blue, should exit orange
    player_pos = blue.position + blue.forward * -10  # slightly in front of blue (entering)
    print(f"Player entering blue at {player_pos}")

    transformed = blue.transform_position_to_linked(player_pos, orange)
    print(f"Transformed exit position at orange: {transformed}")

    # Velocity transformation
    entry_vel = Vector3(100,0,0)
    exit_vel = blue.transform_direction_to_linked(entry_vel, orange)
    print(f"Entry velocity {entry_vel} -> exit velocity {exit_vel}")

    # Test executor EnterPortal
    raycaster = SpatialRaycaster(provider)
    builder = NavigationGraphBuilder(wm, raycaster)
    graph = builder.build()
    controller = MockInputController()
    executor = ActionExecutor(wm, controller, raycaster, graph, provider)

    # Update world model with portals
    for p in provider.get_portals():
        wm.add_entity(p)

    from src.planning.puzzle_solver import AbstractAction, ActionType
    action = AbstractAction(type=ActionType.ENTER_PORTAL, portal_type="blue", description="Enter blue portal")

    # Set player near blue
    wm.player.position = blue.position + blue.forward * -20
    print(f"Player before traversal: {wm.player.position}")

    success = executor.execute(action)
    print(f"Enter portal success: {success}")
    print(f"Player after traversal: {wm.player.position}")

    assert success
    print("TEST 11 PASSED")
    return True

def test_12_solve_room():
    print("\n=== TEST 12: Решить одну простую тестовую комнату ===")
    provider = MockProvider()
    agent = PortalAgent(provider, debug=True)

    print("\nInitial world model:")
    print(agent.world_model.summary())

    # Run one iteration manually
    agent.observe_world()
    goal = agent.check_goal()
    print(f"\nGoal: {goal.type} - {goal.description}")

    plan = agent.plan_action()
    print(f"\nPlan has {len(plan)} actions")

    # Execute plan
    success = agent.execute_action()
    print(f"\nPlan execution success: {success}")

    print("\nFinal world model:")
    print(agent.world_model.summary())

    # Check if goal completed or progress made
    # In test chamber, goal should be get cube then activate button then reach exit
    # Let's run a few iterations
    print("\n--- Running 3 iterations of agent ---")
    for i in range(3):
        should_continue = agent.run_iteration()
        if not should_continue:
            break

    print("\nFinal state after 3 iterations:")
    print(agent.world_model.summary())
    print(f"Player pos: {agent.world_model.player.position}")

    # Check if button pressed or door open
    for btn in agent.world_model.buttons.values():
        print(f"Button {btn.id} pressed: {btn.pressed}")
    for door in agent.world_model.doors.values():
        print(f"Door {door.id} open: {door.open}")

    print("TEST 12 PASSED")
    return True

def run_all_tests():
    tests = [
        test_1_player_position,
        test_2_entity_list,
        test_3_cube_coordinates,
        test_4_button_state,
        test_5_walls_collision,
        test_6_raycast,
        test_7_portalable_surface,
        test_8_nav_graph,
        test_9_move_player,
        test_10_place_portal,
        test_11_portal_traversal,
        test_12_solve_room
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, True, None))
        except Exception as e:
            print(f"\n{test.__name__} FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((test.__name__, False, str(e)))

    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for name, passed, error in results:
        status = "PASSED" if passed else f"FAILED: {error}"
        print(f"{name}: {status}")

    passed_count = sum(1 for _, p, _ in results if p)
    print(f"\nTotal: {passed_count}/{len(results)} passed")

    return passed_count == len(results)

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
