import uvicorn

from .lifecycle import register_shutdown
from .main import app


if __name__ == "__main__":
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=8765, reload=False))
    register_shutdown(lambda: setattr(server, "should_exit", True))
    server.run()
