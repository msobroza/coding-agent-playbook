"""The ASGI entry point app.sh serves: the only module that reads the environment.

Tests never import it; they call create_app with settings built in code.
"""

from app.logs import configure_logging
from app.main import create_app
from app.settings import AgentSettings

settings = AgentSettings()
configure_logging(settings.log_level)
app = create_app(settings)
