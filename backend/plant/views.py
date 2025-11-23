import os
import json

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.conf import settings

from shapely.geometry import shape
from shapely.geometry import MultiPolygon

from .models import Plant
from .serializers import PlantSerializer
from .dxf_parser import parse_dxf_to_geojson
from .report import generate_report_pdf

UNITS_TO_METERS = 0.001
TARGET_LAYERS_FOR_AREA = ["VS - Parede"]


class PlantViewSet(viewsets.ModelViewSet):
    queryset = Plant.objects.all()
    serializer_class = PlantSerializer

    # ----------------------------------------
    # GET /plants/{id}/coordinates/
    # ----------------------------------------
    @action(detail=True, methods=["get"])
    def coordinates(self, request, pk=None):
        plant = self.get_object()
        try:
            geojson_str, metadata, multipolygon = parse_dxf_to_geojson(
                plant.dxf_file.path,
                scale_factor=UNITS_TO_METERS,
                target_layers=TARGET_LAYERS_FOR_AREA,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"geojson": json.loads(geojson_str), "metadata": metadata})

    # ----------------------------------------
    # GET /plants/{id}/metrics/
    # ----------------------------------------
    @action(detail=True, methods=["get"])
    def metrics(self, request, pk=None):
        plant = self.get_object()

        try:
            geojson_str, metadata, multipolygon = parse_dxf_to_geojson(
                plant.dxf_file.path,
                scale_factor=UNITS_TO_METERS,
                target_layers=TARGET_LAYERS_FOR_AREA,
            )

            if isinstance(multipolygon, MultiPolygon):
                polygons = list(multipolygon.geoms)
            else:
                polygons = [multipolygon]

            total_area = round(sum(p.area * (UNITS_TO_METERS**2) for p in polygons), 3)
            total_perimeter = round(
                sum(p.length * UNITS_TO_METERS for p in polygons), 3
            )
            total_vertices = sum(len(p.exterior.coords) for p in polygons)

            result = {
                "area_m2": total_area,
                "perimeter_m": total_perimeter,
                "vertices": total_vertices,
                "metadata": metadata,
            }

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(result)

    # ----------------------------------------
    # GET /plants/{id}/calculate/
    # ----------------------------------------
    @action(detail=True, methods=["get"])
    def calculate(self, request, pk=None):
        plant = self.get_object()

        try:
            geojson_str, metadata, multipolygon = parse_dxf_to_geojson(
                plant.dxf_file.path,
                scale_factor=UNITS_TO_METERS,
                target_layers=TARGET_LAYERS_FOR_AREA,
            )

            if isinstance(multipolygon, MultiPolygon):
                polygons = list(multipolygon.geoms)
            else:
                polygons = [multipolygon]

            total_area = round(sum(p.area * (UNITS_TO_METERS**2) for p in polygons), 3)
            total_perimeter = round(
                sum(p.length * UNITS_TO_METERS for p in polygons), 3
            )
            total_vertices = sum(len(p.exterior.coords) for p in polygons)

            result = {
                "area_m2": total_area,
                "perimeter_m": total_perimeter,
                "vertices": total_vertices,
                "metadata": metadata,
            }

        except Exception as e:
            return Response({"error": str(e)}, status=400)

        return Response(result)

    # ----------------------------------------
    # GET /plants/{id}/report/
    # ----------------------------------------
    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        plant = self.get_object()

        try:
            geojson_area, metadata_area, polygons_area = parse_dxf_to_geojson(
                plant.dxf_file.path,
                scale_factor=UNITS_TO_METERS,
                target_layers=TARGET_LAYERS_FOR_AREA,
            )

            geojson_drawing, _, _ = parse_dxf_to_geojson(
                plant.dxf_file.path, scale_factor=1.0, target_layers=None
            )

            constructions = metadata_area.get("constructions", [])

            if not constructions:
                total_area = 0.0
                total_perimeter = 0.0
                total_vertices = 0
            else:
                total_area = round(sum(c["area"] for c in constructions), 3)
                total_perimeter = round(sum(c["perimeter"] for c in constructions), 3)
                total_vertices = sum(c["vertices"] for c in constructions)

            metadata_area.update(
                {
                    "total_area_m2": total_area,
                    "total_perimeter_m": total_perimeter,
                    "total_vertices": total_vertices,
                }
            )

            pdf_path = generate_report_pdf(
                metadata_area,
                plant.name,
                geojson_str=geojson_drawing,  # <--- GeoJSON COMPLETO
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        pdf_url = request.build_absolute_uri(
            settings.MEDIA_URL + "reports/" + os.path.basename(pdf_path)
        )

        return Response({"pdf": pdf_url, "metadata": metadata_area})
