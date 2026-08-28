"""
SDK API views.
"""
import asyncio
import hashlib
import json

from asgiref.sync import sync_to_async
from django.db import connection
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from core_flags.models import FeatureFlag
from core_flags.notifications import asubscribe_to_flags
from core_flags.services import FlagEvaluationService
from sdk_api.authentication import IsSDKAuthenticated
from sdk_api.models import EvaluationLog, SDKRegistration
from sdk_api.payloads import serialize_environment_flags

# How long a subscribed stream waits before sending a keepalive, so proxies do
# not close an idle connection.
KEEPALIVE_SECONDS = 15
# Only used when Redis is unavailable and the stream has to ask the database.
POLL_SECONDS = 2


@api_view(["GET"])
@permission_classes([IsSDKAuthenticated])
def sdk_flags(request):
    """
    Get all flags for the authenticated environment.

    Returns flags with their current state for local evaluation.
    """
    environment = request.user  # SDKAuthentication returns Environment

    flags_data = serialize_environment_flags(environment)

    return Response({"flags": flags_data}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsSDKAuthenticated])
def sdk_evaluate(request):
    """
    Evaluate flags with context.

    POST body:
    {
        "context": {"country": "US", "plan": "premium"}
    }

    Returns evaluation results for all flags.
    """
    environment = request.user
    context = request.data.get("context", {})

    service = FlagEvaluationService()
    flags = FeatureFlag.objects.filter(environment=environment).prefetch_related(
        "rules", "rules__conditions"
    )

    results = []
    for flag in flags:
        result = service.evaluate_flag(flag, context)

        # Log evaluation
        context_hash = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()[
            :64
        ]
        EvaluationLog.objects.create(
            flag=flag,
            context_hash=context_hash,
            result=bool(result),
        )

        results.append(
            {
                "key": flag.key,
                "value": result,
            }
        )

    return Response({"results": results}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsSDKAuthenticated])
def sdk_register(request):
    """
    Register SDK instance.

    POST body:
    {
        "sdk_type": "PYTHON",
        "version": "1.0.0"
    }
    """
    environment = request.user
    sdk_type = request.data.get("sdk_type")
    sdk_version = request.data.get("version")

    if not sdk_type or not sdk_version:
        return Response(
            {"error": "sdk_type and version are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Create or update registration
    registration, created = SDKRegistration.objects.update_or_create(
        environment=environment,
        sdk_type=sdk_type,
        defaults={"version": sdk_version},
    )

    return Response(
        {
            "status": "registered",
            "sdk_key": registration.sdk_key,
            "created": created,
        },
        status=status.HTTP_201_CREATED,
    )


async def sdk_stream(request):
    """
    SSE stream for real-time flag updates.

    Written as an async view on purpose. Under ASGI a synchronous generator is
    not streamed out chunk by chunk: the client receives the response headers
    and then nothing, because this generator never finishes. That looks like a
    healthy connection from the outside while no event is ever delivered.
    """
    from django.http import JsonResponse

    # EventSource can't send headers, so check query param first
    api_key = request.GET.get("api_key") or request.META.get("HTTP_X_API_KEY")
    if not api_key:
        return JsonResponse({"detail": "Authentication credentials were not provided."}, status=401)

    from core_flags.models import Environment

    try:
        environment = await Environment.objects.aget(api_key=api_key)
    except Environment.DoesNotExist:
        return JsonResponse({"detail": "Invalid API key."}, status=401)

    def _read_flags():
        """
        Read the environment's flags, then hand the database connection back.

        A stream only touches the database on connect and on change, but the
        worker thread that does it keeps its connection for as long as it
        lives. Holding one per connected client exhausts max_connections long
        before the server runs out of capacity, and the symptom is a stream
        that connects and then receives nothing.
        """
        try:
            return {
                payload["key"]: payload
                for payload in serialize_environment_flags(environment)
            }
        finally:
            connection.close()

    read_flags = sync_to_async(_read_flags)

    async def event_stream():
        """Generate SSE events."""
        yield f"event: connected\ndata: {json.dumps({'status': 'connected', 'environment': str(environment.key)})}\n\n"

        last_flags = await read_flags()
        yield f"event: flags\ndata: {json.dumps({'flags': list(last_flags.values())})}\n\n"

        subscription = await asubscribe_to_flags(environment.id)

        try:
            while True:
                if subscription is not None:
                    # Woken by a write rather than asking. Costs no query while
                    # nothing changes, and arrives without the polling delay.
                    changed = await subscription.wait(KEEPALIVE_SECONDS)
                else:
                    # Without Redis there is nobody to wake us, so fall back to
                    # asking the database on an interval.
                    await asyncio.sleep(POLL_SECONDS)
                    changed = True

                if not changed:
                    yield ": keepalive\n\n"
                    continue

                current_flags = await read_flags()
                if current_flags != last_flags:
                    last_flags = current_flags
                    yield f"event: flags\ndata: {json.dumps({'flags': list(current_flags.values())})}\n\n"
                else:
                    yield ": keepalive\n\n"
        finally:
            if subscription is not None:
                await subscription.close()

    response = StreamingHttpResponse(
        event_stream(),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
