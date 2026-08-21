from django.utils import timezone
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView, exception_handler

from core.authentication import SessionOrApiKeyAuthentication
from core.permissions import IsAuthenticatedOrServiceKey


class ServiceError(APIException):
    """Raised by any services.py function to signal a failure that should
    render as the {ok:false, message} envelope, mirroring FastAPI-era
    core.responses.fail(). status_code defaults to 502 (bad upstream) to
    match the old default; pass status= to override (404, 409, etc.)."""

    def __init__(self, message: str, status: int = 502):
        self.status_code = status
        super().__init__(detail=message)


def envelope_exception_handler(exc, context):
    if not isinstance(exc, ServiceError):
        return exception_handler(exc, context)
    return Response({"ok": False, "message": str(exc.detail)}, status=exc.status_code)


class EnvelopeAPIView(APIView):
    authentication_classes = [SessionOrApiKeyAuthentication]
    permission_classes = [IsAuthenticatedOrServiceKey]

    def ok(self, message: str, **extra) -> Response:
        return Response({
            "ok": True,
            "message": message,
            "time": timezone.now().strftime("%H:%M:%S"),
            **extra,
        })
