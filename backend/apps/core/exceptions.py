"""Uniform error envelope: {"error": {"code", "message", "fields"}}. Field errors are flat lists of strings."""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("daywell.errors")


class BusinessRuleError(exceptions.APIException):
    """A valid request that conflicts with the current state (e.g. completing a cancelled task)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "This action is not allowed in the current state."
    default_code = "conflict"

    def __init__(self, detail: str | None = None, code: str | None = None, status_code: int | None = None):
        super().__init__(detail, code)
        if status_code:
            self.status_code = status_code
        if code:
            self.error_code = code


def _flatten(detail) -> list[str]:
    if isinstance(detail, list):
        out: list[str] = []
        for item in detail:
            out.extend(_flatten(item))
        return out
    if isinstance(detail, dict):
        out = []
        for key, value in detail.items():
            out.extend(f"{key}: {msg}" for msg in _flatten(value))
        return out
    return [str(detail)]


def _is_infrastructure_outage(exc) -> bool:
    """Database or cache/broker connectivity failures (not bugs): answer 503 so clients and monitors can tell them apart."""
    from django.db import InterfaceError, OperationalError
    from redis.exceptions import ConnectionError as RedisConnectionError
    from redis.exceptions import TimeoutError as RedisTimeoutError

    return isinstance(exc, (OperationalError, InterfaceError, RedisConnectionError, RedisTimeoutError))


def envelope_exception_handler(exc, context):
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()
    elif isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)

    response = exception_handler(exc, context)
    if response is None and _is_infrastructure_outage(exc):
        logger.error("Dependency unavailable: %s", exc.__class__.__name__, exc_info=exc)
        response = Response(
            {"error": {"code": "service_unavailable", "message": "DayWell is temporarily unavailable. Your data is safe — please try again in a minute.", "fields": {}}},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        response["Retry-After"] = "30"
        return response
    if response is None:
        logger.exception("Unhandled API error", exc_info=exc)
        return Response(
            {"error": {"code": "server_error", "message": "Something went wrong on our side. Please try again.", "fields": {}}},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    fields: dict[str, list[str]] = {}
    message = ""
    code = getattr(exc, "error_code", None) or getattr(exc, "default_code", "error")
    if isinstance(exc, exceptions.ValidationError) and isinstance(exc.detail, dict):
        for key, value in exc.detail.items():
            msgs = _flatten(value)
            if key in ("non_field_errors", "detail"):
                message = message or (msgs[0] if msgs else "")
            fields[key] = msgs
        message = message or "Please correct the highlighted fields."
        code = "validation_error"
    elif isinstance(exc, exceptions.ValidationError):
        msgs = _flatten(exc.detail)
        message = msgs[0] if msgs else "Invalid input."
        fields = {"non_field_errors": msgs}
        code = "validation_error"
    else:
        detail = getattr(exc, "detail", None)
        message = " ".join(_flatten(detail)) if detail is not None else str(exc)
    response.data = {"error": {"code": str(code), "message": message, "fields": fields}}
    return response
