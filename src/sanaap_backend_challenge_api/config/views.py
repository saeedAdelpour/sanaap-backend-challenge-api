"""Operational endpoints."""

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@extend_schema(
    tags=["Health"],
    responses=inline_serializer(
        name="Health", fields={"status": serializers.ChoiceField(choices=["ok"])}
    ),
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    """Public liveness probe; does not check database or storage readiness."""
    return Response({"status": "ok"})


class LoginView(ObtainAuthToken):
    @extend_schema(
        tags=["Authentication"],
        auth=[],
        responses={
            200: inline_serializer(
                name="AuthToken", fields={"token": serializers.CharField()}
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
