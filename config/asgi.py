"""
ASGI config for flagward project.
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_asgi_application()

# After the app is built so settings and apps are loaded. Only server processes
# import this module, which is why telemetry starts here and not in an AppConfig.
from telemetry.runtime import start as start_telemetry  # noqa: E402

start_telemetry(server='asgi')
