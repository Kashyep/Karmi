from daily_agent.parakh.routing import KNOWN_ACTIONS, ROUTE_ACTIONS, model_registry


def test_every_executable_route_action_is_known_and_has_a_registry_entry() -> None:
    registry_actions = {f"{m['provider']}/{m['model']}" for m in model_registry()}
    for action in ROUTE_ACTIONS.values():
        assert action in KNOWN_ACTIONS
        assert action in registry_actions
