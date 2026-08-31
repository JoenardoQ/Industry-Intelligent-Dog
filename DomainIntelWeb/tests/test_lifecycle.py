from DomainIntelWeb.api.lifecycle import register_shutdown, request_shutdown


def test_registered_server_shutdown_is_platform_neutral():
    state = {"stopping": False}
    register_shutdown(lambda: state.update(stopping=True))
    try:
        request_shutdown()
        assert state["stopping"] is True
    finally:
        register_shutdown(None)
