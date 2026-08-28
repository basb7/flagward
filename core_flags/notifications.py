"""
Change notifications for the SDK's live update stream.

The stream used to ask the database every two seconds whether anything had
changed. That cost one query per connected client per two seconds whether or not
anything happened, and still left a client up to two seconds behind.

Redis carries the notification instead: a write publishes, a stream wakes. When
Redis is not configured the stream falls back to polling, so REDIS_URL stays
optional and nothing here is ever allowed to break a write.
"""
import logging
import os
import time

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "flagward:flags"


def channel_for(environment_id) -> str:
    """The channel one environment's changes are published on."""
    return f"{CHANNEL_PREFIX}:{environment_id}"


def redis_url() -> str | None:
    """The configured Redis URL, if there is one."""
    return os.getenv("REDIS_URL") or None


def is_available() -> bool:
    """Whether notifications can be used at all."""
    return redis_url() is not None


def _client():
    """A Redis client, or None if Redis is not configured or not importable."""
    url = redis_url()
    if url is None:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
    except Exception:
        logger.warning("Could not create a Redis client", exc_info=True)
        return None


def publish_flags_changed(environment_id) -> bool:
    """
    Announce that an environment's flags changed. Returns whether it was sent.

    Called from a signal, so it runs inside the transaction that saved a flag.
    A Redis that is down must not turn a successful save into a 500, which is
    why every failure here is swallowed and logged: subscribers fall back to
    their own refresh, and the worst case is a stale client, not a lost write.
    """
    client = _client()
    if client is None:
        return False

    try:
        client.publish(channel_for(environment_id), "changed")
        return True
    except Exception:
        logger.warning(
            "Could not publish a flag change for environment %s",
            environment_id,
            exc_info=True,
        )
        return False
    finally:
        try:
            client.close()
        except Exception:
            pass


class FlagChangeSubscription:
    """
    A subscription to one environment's changes.

    `wait` blocks for up to `timeout` seconds and reports whether a change
    arrived, so the caller can send a keepalive when it did not.
    """

    def __init__(self, pubsub):
        self._pubsub = pubsub

    def wait(self, timeout: float) -> bool:
        """
        Block until a change arrives or `timeout` passes.

        Redis interleaves its own subscribe confirmations with real messages,
        and get_message returns as soon as it sees one. Waiting against a
        deadline rather than a single call keeps that bookkeeping from being
        mistaken for a change, or from cutting the wait short.
        """
        deadline = time.monotonic() + timeout

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False

            try:
                message = self._pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=remaining
                )
            except Exception:
                logger.warning("Flag change subscription failed", exc_info=True)
                return False

            if message is not None:
                return True

    def close(self) -> None:
        try:
            self._pubsub.close()
        except Exception:
            pass


def subscribe_to_flags(environment_id) -> FlagChangeSubscription | None:
    """Subscribe to an environment's changes, or None if that is not possible."""
    client = _client()
    if client is None:
        return None

    try:
        pubsub = client.pubsub()
        pubsub.subscribe(channel_for(environment_id))
        return FlagChangeSubscription(pubsub)
    except Exception:
        logger.warning(
            "Could not subscribe to flag changes for environment %s",
            environment_id,
            exc_info=True,
        )
        return None


class AsyncFlagChangeSubscription:
    """
    The same subscription for an async stream.

    Waiting through a thread would put one blocked thread behind every
    connected client, which is the cost the async server exists to avoid.
    """

    def __init__(self, client, pubsub):
        self._client = client
        self._pubsub = pubsub

    async def wait(self, timeout: float) -> bool:
        """Block until a change arrives or `timeout` passes."""
        deadline = time.monotonic() + timeout

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False

            try:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=remaining
                )
            except Exception:
                logger.warning("Flag change subscription failed", exc_info=True)
                return False

            if message is not None:
                return True

    async def close(self) -> None:
        for closing in (self._pubsub.aclose(), self._client.aclose()):
            try:
                await closing
            except Exception:
                pass


async def asubscribe_to_flags(environment_id) -> AsyncFlagChangeSubscription | None:
    """Subscribe to an environment's changes from async code."""
    url = redis_url()
    if url is None:
        return None

    try:
        import redis.asyncio as aioredis

        client = aioredis.Redis.from_url(url)
        pubsub = client.pubsub()
        await pubsub.subscribe(channel_for(environment_id))
        return AsyncFlagChangeSubscription(client, pubsub)
    except Exception:
        logger.warning(
            "Could not subscribe to flag changes for environment %s",
            environment_id,
            exc_info=True,
        )
        return None
