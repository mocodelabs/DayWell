from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.timeutils import get_zone, local_today

from . import planner, services


class TodayView(APIView):
    """GET /api/v1/dashboard/today/ — the structured daily briefing built from real records."""

    def get(self, request):
        return Response(services.today_payload(request.user))


class PlanDaySerializer(serializers.Serializer):
    date = serializers.DateField(required=False)


class PlanItemSerializer(serializers.Serializer):
    task_id = serializers.IntegerField()
    start_time = serializers.TimeField()


class ApplyPlanSerializer(serializers.Serializer):
    date = serializers.DateField()
    items = PlanItemSerializer(many=True, min_length=1, max_length=50)


class PlannerSuggestView(APIView):
    def get(self, request):
        ser = PlanDaySerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        day = ser.validated_data.get("date") or local_today(get_zone(request.user.preferences.time_zone))
        return Response(planner.suggest(request.user, day))


class PlannerApplyView(APIView):
    def post(self, request):
        ser = ApplyPlanSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ids = planner.apply(request.user, ser.validated_data["date"], ser.validated_data["items"])
        return Response({"updated": ids})
