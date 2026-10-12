"""Owner scoping. Every user-data viewset derives from OwnedModelViewSet so cross-user access is impossible by construction."""

from rest_framework import serializers, viewsets


class OwnedQuerysetMixin:
    """Restrict the queryset to the authenticated user and stamp ownership on create.

    Never trust a client-supplied owner: `owner` is not a writable serializer field anywhere.
    Objects belonging to someone else therefore 404 (no existence oracle) rather than 403.
    """

    owner_field = "owner"

    def get_queryset(self):
        return super().get_queryset().filter(**{self.owner_field: self.request.user})

    def perform_create(self, serializer):
        serializer.save(**{self.owner_field: self.request.user})


class OwnedModelViewSet(OwnedQuerysetMixin, viewsets.ModelViewSet):
    pass


class OwnedPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """A FK field whose choices are limited to the requesting user's own rows (blocks linking to someone else's record)."""

    def __init__(self, *args, owner_field: str = "owner", **kwargs):
        self.owner_field = owner_field
        super().__init__(*args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return qs.none()
        return qs.filter(**{self.owner_field: request.user})
