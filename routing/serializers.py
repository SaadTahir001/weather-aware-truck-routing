from rest_framework import serializers


class RouteCalculationRequestSerializer(serializers.Serializer):
    origin = serializers.CharField(max_length=256, trim_whitespace=True)
    destination = serializers.CharField(max_length=256, trim_whitespace=True)
    departure_time = serializers.DateTimeField()
    load_weight_lb = serializers.IntegerField(min_value=0)

    def validate(self, attrs):
        if attrs["origin"].casefold() == attrs["destination"].casefold():
            raise serializers.ValidationError(
                "Origin and destination must be different."
            )
        return attrs


class CoordinateSerializer(serializers.Serializer):
    longitude = serializers.FloatField()
    latitude = serializers.FloatField()


class ResolvedLocationSerializer(serializers.Serializer):
    query = serializers.CharField()
    display_name = serializers.CharField()
    coordinate = CoordinateSerializer()


class ResolvedLocationsSerializer(serializers.Serializer):
    origin = ResolvedLocationSerializer()
    destination = ResolvedLocationSerializer()


class GeometrySerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=("LineString",))
    coordinates = serializers.ListField(
        child=serializers.ListField(
            child=serializers.FloatField(), min_length=2, max_length=2
        )
    )


class WeatherSerializer(serializers.Serializer):
    forecast_time = serializers.DateTimeField()
    wind_mph = serializers.FloatField()
    rain_in_per_hour = serializers.FloatField()
    snow_in_per_hour = serializers.FloatField()
    temperature_f = serializers.FloatField(allow_null=True)
    description = serializers.CharField(allow_blank=True)


class RiskBreakdownSerializer(serializers.Serializer):
    wind = serializers.CharField()
    rain = serializers.CharField()
    snow = serializers.CharField()
    overall = serializers.CharField()


class CheckpointResultSerializer(serializers.Serializer):
    sequence = serializers.IntegerField()
    coordinate = CoordinateSerializer()
    eta = serializers.DateTimeField()
    segment_distance_miles = serializers.FloatField()
    weather = WeatherSerializer()
    risk = RiskBreakdownSerializer()


class RankingSerializer(serializers.Serializer):
    severe_miles = serializers.FloatField()
    high_miles = serializers.FloatField()
    average_risk = serializers.FloatField()
    travel_seconds = serializers.FloatField()


class DecisionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=("recommended", "not_recommended", "rejected")
    )
    reason = serializers.CharField()


class RouteResultSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    geometry = GeometrySerializer()
    distance_miles = serializers.FloatField()
    duration_seconds = serializers.FloatField()
    arrival_time = serializers.DateTimeField()
    eligible = serializers.BooleanField()
    ranking = RankingSerializer()
    decision = DecisionSerializer()
    checkpoints = CheckpointResultSerializer(many=True)


class RouteCalculationResponseSerializer(serializers.Serializer):
    data_source = serializers.ChoiceField(choices=("live", "mock"))
    mock_reason = serializers.CharField(allow_null=True)
    request = RouteCalculationRequestSerializer()
    resolved_locations = ResolvedLocationsSerializer()
    recommended_route_id = serializers.CharField(allow_null=True)
    recommendation_summary = serializers.CharField()
    ranking_hierarchy = serializers.ListField(child=serializers.CharField())
    routes = RouteResultSerializer(many=True)
