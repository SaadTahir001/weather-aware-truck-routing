from django.urls import path

from .views import RouteCalculationView


app_name = "routing"

urlpatterns = [
    path(
    "routes/calculate/",
    RouteCalculationView.as_view(),
    name="calculate-routes",
),
]
