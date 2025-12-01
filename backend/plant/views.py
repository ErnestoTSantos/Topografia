import os
import json
import math

from django.http import HttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.conf import settings

from .models import Plant
from .serializers import PlantSerializer
from .dxf_parser import parse_dxf_to_geojson
from .report import generate_report_pdf, fetch_topography_by_cep

UNITS_TO_METERS = 1.839

DRAWING_SCALE = 50

DXF_REF_X = 10.0
DXF_REF_Y = 10.0
GLOBAL_REF_LAT = -29.812345
GLOBAL_REF_LONG = -51.234567

TARGET_LAYERS_GROUND_FLOOR = ["ALVENARIA_TERREO", "0"]
TARGET_LAYERS_FIRST_FLOOR = ["ALVENARIA_1_PISO", "0"]


class PlantViewSet(viewsets.ModelViewSet):
    queryset = Plant.objects.all()
    serializer_class = PlantSerializer

    def _convert_dxf_to_latlong(self, x_dxf, y_dxf):
        """Simple georeferencing function (placeholder: assumes no rotation)."""

        dx_m = (x_dxf - DXF_REF_X) * UNITS_TO_METERS
        dy_m = (y_dxf - DXF_REF_Y) * UNITS_TO_METERS

        lat_per_m = 1.0 / 111132.0
        long_per_m = 1.0 / (111132.0 * math.cos(math.radians(GLOBAL_REF_LAT)))

        latitude = GLOBAL_REF_LAT + (dy_m * lat_per_m)
        longitude = GLOBAL_REF_LONG + (dx_m * long_per_m)

        return latitude, longitude

    def extract_coords_from_geojson(self, geojson_obj):
        coords = []
        for feature in geojson_obj.get("features", []):
            geom = feature.get("geometry", {})
            if geom.get("type") in ("Polygon", "LineString"):
                c = (
                    geom["coordinates"][0]
                    if geom.get("type") == "Polygon"
                    else geom["coordinates"]
                )
                for p in c:
                    coords.append({"x": p[0], "y": p[1]})
        return coords

    # ----------------------------------------
    # 1) GET /plants/{id}/geojson/
    # ----------------------------------------
    @action(detail=True, methods=["get"])
    def geojson(self, request, pk=None):
        """Returns the full processed GeoJSON from the DXF."""
        plant = self.get_object()

        try:
            geojson_str, metadata, _ = parse_dxf_to_geojson(
                plant.dxf_file.path,
                scale_factor=UNITS_TO_METERS,
                target_layers=None,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(json.loads(geojson_str))

    # ----------------------------------------
    # 2) GET /plants/{id}/download_geojson/
    # ----------------------------------------
    @action(detail=True, methods=["get"])
    def download_geojson(self, request, pk=None):
        """Downloads the GeoJSON as a file."""
        plant = self.get_object()

        try:
            geojson_str, _, _ = parse_dxf_to_geojson(
                plant.dxf_file.path,
                scale_factor=UNITS_TO_METERS,
                target_layers=None,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        response = HttpResponse(geojson_str, content_type="application/json")
        response["Content-Disposition"] = f'attachment; filename="{plant.name}.geojson"'
        return response

    # ----------------------------------------
    # 3) GET /plants/{id}/metrics/
    # ----------------------------------------
    @action(detail=True, methods=["get"])
    def metrics(self, request, pk=None):
        """Returns area and perimeter metrics for both the Ground and First Floors."""
        plant = self.get_object()

        try:
            _, metadata_a, _ = parse_dxf_to_geojson(
                plant.dxf_file.path,
                scale_factor=UNITS_TO_METERS,
                target_layers=TARGET_LAYERS_GROUND_FLOOR,
            )

            _, metadata_b, _ = parse_dxf_to_geojson(
                plant.dxf_file.path,
                scale_factor=UNITS_TO_METERS,
                target_layers=TARGET_LAYERS_FIRST_FLOOR,
            )

            area_a = sum(
                c.get("area", 0.0) for c in metadata_a.get("constructions", [])
            )
            area_b = sum(
                c.get("area", 0.0) for c in metadata_b.get("constructions", [])
            )

            perimeter_a = metadata_a.get("total_perimeter_m", 0.0)
            perimeter_b = metadata_b.get("total_perimeter_m", 0.0)

            vertices_a = sum(
                c.get("vertices", 0) for c in metadata_a.get("constructions", [])
            )
            vertices_b = sum(
                c.get("vertices", 0) for c in metadata_b.get("constructions", [])
            )

            total_area_m2 = area_a + area_b
            total_perimeter_m = perimeter_a + perimeter_b
            total_vertices = vertices_a + vertices_b

            result = {
                "area_m2_ground_floor": round(area_a, 3),
                "perimeter_m_ground_floor": round(perimeter_a, 3),
                "area_m2_first_floor": round(area_b, 3),
                "perimeter_m_first_floor": round(perimeter_b, 3),
                "total_area_m2_global": round(total_area_m2, 3),
                "total_perimeter_m_global": round(total_perimeter_m, 3),
                "total_vertices": total_vertices,
                "metadata_ground_floor": metadata_a,
                "metadata_first_floor": metadata_b,
            }

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(result)

    # ----------------------------------------
    # 4) GET /plants/{id}/layers/
    # ----------------------------------------
    @action(detail=True, methods=["get"])
    def layers(self, request, pk=None):
        """Returns metadata organized by layer."""
        plant = self.get_object()

        try:
            _, metadata, _ = parse_dxf_to_geojson(
                plant.dxf_file.path,
                scale_factor=UNITS_TO_METERS,
                target_layers=None,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        layers = metadata.get("layers", {})
        return Response(layers)

    # ----------------------------------------
    # 5) GET /plants/{id}/report/
    # ----------------------------------------
    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        """Generates the full PDF report and returns metadata, including external topography data."""
        plant = self.get_object()

        try:
            geojson_drawing, metadata_full, _ = parse_dxf_to_geojson(
                plant.dxf_file.path, scale_factor=UNITS_TO_METERS, target_layers=None
            )

            total_area = sum(
                c.get("area", 0.0) for c in metadata_full.get("constructions", [])
            )
            total_perimeter = sum(
                c.get("perimeter", 0.0) for c in metadata_full.get("constructions", [])
            )
            total_vertices = sum(
                c.get("vertices", 0) for c in metadata_full.get("constructions", [])
            )

            topo_external = fetch_topography_by_cep(plant.cep)

            metadata_full.update(
                {
                    "total_area_m2": round(total_area, 3),
                    "total_perimeter_m": round(total_perimeter, 3),
                    "total_vertices": total_vertices,
                    "drawing_scale": DRAWING_SCALE,
                    "scale_factor_used": UNITS_TO_METERS,
                }
            )

            pdf_path = generate_report_pdf(
                metadata_full,
                plant.name,
                cep=plant.cep,
                house_number=plant.number,
                geojson_str=geojson_drawing,
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        pdf_url = request.build_absolute_uri(
            settings.MEDIA_URL + "reports/" + os.path.basename(pdf_path)
        )

        if topo_external:
            metadata_full.setdefault("topography", {})
            metadata_full["topography"]["external"] = topo_external

        return Response({"pdf": pdf_url, "metadata": metadata_full})
