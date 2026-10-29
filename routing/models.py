from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Route(models.Model):
    """A candidate route whose checkpoints are evaluated at their ETAs."""

    name = models.CharField(max_length=120)
    external_id = models.CharField(
        max_length=120,
        blank=True,
        db_index=True,
        help_text="Optional identifier from the map/routing provider.",
    )
    origin = models.CharField(max_length=255)
    destination = models.CharField(max_length=255)
    total_distance_miles = models.DecimalField(
        max_digits=9,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    planned_departure = models.DateTimeField()
    planned_arrival = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "id")

    def __str__(self) -> str:
        return self.name

    @property
    def planned_travel_seconds(self) -> float:
        return max(
            0.0,
            (self.planned_arrival - self.planned_departure).total_seconds(),
        )


class Checkpoint(models.Model):
    """
    Forecast conditions at a point on a candidate route.

    The checkpoint's weather applies to ``segment_distance_miles`` miles after
    that checkpoint. The destination checkpoint should therefore have a segment
    distance of zero. This makes miles-by-risk-level deterministic.
    """

    route = models.ForeignKey(
        Route,
        on_delete=models.CASCADE,
        related_name="checkpoints",
    )
    sequence = models.PositiveIntegerField()
    name = models.CharField(max_length=120, blank=True)
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[
            MinValueValidator(Decimal("-90")),
            MaxValueValidator(Decimal("90")),
        ],
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[
            MinValueValidator(Decimal("-180")),
            MaxValueValidator(Decimal("180")),
        ],
    )
    eta = models.DateTimeField(
        db_index=True,
        help_text="Forecast time to use when evaluating this checkpoint.",
    )
    segment_distance_miles = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Miles from this checkpoint to the next checkpoint.",
    )
    wind_mph = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    rain_in_per_hour = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    snow_in_per_hour = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        ordering = ("route_id", "sequence")
        constraints = [
            models.UniqueConstraint(
                fields=("route", "sequence"),
                name="routing_unique_checkpoint_sequence",
            )
        ]

    def __str__(self) -> str:
        label = self.name or f"Checkpoint {self.sequence}"
        return f"{self.route.name}: {label}"
