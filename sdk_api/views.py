"""
SDK API views.
"""
import hashlib
import json

from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from core_flags.models import FeatureFlag
from core_flags.services import FlagEvaluationService
from sdk_api.authentication import IsSDKAuthenticated
from sdk_api.models import EvaluationLog, SDKRegistration
from sdk_api.payloads import serialize_environment_flags


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


def sdk_stream(request):
    """
    SSE stream for real-time flag updates.

    Streams flag changes as they happen.
    This is a plain Django view (not DRF) because DRF doesn't support async streaming.
    """
    # EventSource can't send headers, so check query param first
    api_key = request.GET.get("api_key") or request.META.get("HTTP_X_API_KEY")
    if not api_key:
        from django.http import JsonResponse
        return JsonResponse({"detail": "Authentication credentials were not provided."}, status=401)

    from core_flags.models import Environment

    try:
        environment = Environment.objects.get(api_key=api_key)
    except Environment.DoesNotExist:
        from django.http import JsonResponse
        return JsonResponse({"detail": "Invalid API key."}, status=401)

    def event_stream():
        """Generate SSE events."""
        import time

        # Send initial connection event
        yield f"event: connected\ndata: {json.dumps({'status': 'connected', 'environment': str(environment.key)})}\n\n"

        def get_current_flags():
            return {
                payload["key"]: payload
                for payload in serialize_environment_flags(environment)
            }

        last_flags = get_current_flags()
        yield f"event: flags\ndata: {json.dumps({'flags': list(last_flags.values())})}\n\n"

        # Poll for changes every 2 seconds
        while True:
            time.sleep(2)
            current_flags = get_current_flags()

            if current_flags != last_flags:
                last_flags = current_flags
                yield f"event: flags\ndata: {json.dumps({'flags': list(current_flags.values())})}\n\n"
            else:
                # Keepalive when no changes
                yield ": keepalive\n\n"

    response = StreamingHttpResponse(
        event_stream(),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
