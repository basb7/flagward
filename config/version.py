"""
The Flagward release this source tree belongs to.

Bumped as part of every release. It lives in code rather than in a Docker
build argument because operators build their image from source through
compose.yml, where a build argument would almost always be empty.
"""
__version__ = "0.7.1"
