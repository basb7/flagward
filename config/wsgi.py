"""
WSGI config for flagward project.
"""
import os
import sys

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()

# After the app is built so settings and apps are loaded. Only server processes
# (including `runserver`) import this module, which is why telemetry starts here
# and not in an AppConfig.
from telemetry.runtime import start as start_telemetry  # noqa: E402
from telemetry.runtime import wsgi_server_name  # noqa: E402

start_telemetry(server=wsgi_server_name(sys.argv))
