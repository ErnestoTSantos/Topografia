import os
import json

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.conf import settings

from shapely.geometry import shape, MultiPolygon

from .models import Plant
from .serializers import PlantSerializer
from .dxf_parser import parse_dxf_to_geojson
from .report import generate_report_pdf


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
                plant.dxf_file.path
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
                plant.dxf_file.path
            )

            if isinstance(multipolygon, MultiPolygon):
                polygons = list(multipolygon.geoms)
            else:
                polygons = [multipolygon]

            total_area = round(sum(p.area for p in polygons), 3)
            total_perimeter = round(sum(p.length for p in polygons), 3)
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
                plant.dxf_file.path
            )

            if isinstance(multipolygon, MultiPolygon):
                polygons = list(multipolygon.geoms)
            else:
                polygons = [multipolygon]

            result = {
                "area_m2": round(sum(p.area for p in polygons), 3),
                "perimeter_m": round(sum(p.length for p in polygons), 3),
                "vertices": sum(len(p.exterior.coords) for p in polygons),
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
            geojson_str, metadata, multipolygon = parse_dxf_to_geojson(
                plant.dxf_file.path
            )

            constructions = metadata.get("constructions", [])

            if not constructions:
                if isinstance(multipolygon, MultiPolygon):
                    polygons = list(multipolygon.geoms)
                else:
                    polygons = [multipolygon]

                constructions = [
                    {
                        "area": round(p.area, 3),
                        "perimeter": round(p.length, 3),
                        "vertices": len(p.exterior.coords),
                    }
                    for p in polygons
                ]

                metadata["constructions"] = constructions

            total_area = round(sum(c["area"] for c in constructions), 3)
            total_perimeter = round(sum(c["perimeter"] for c in constructions), 3)
            total_vertices = sum(c["vertices"] for c in constructions)

            metadata.update(
                {
                    "total_area_m2": total_area,
                    "total_perimeter_m": total_perimeter,
                    "total_vertices": total_vertices,
                }
            )

            pdf_path = generate_report_pdf(
                metadata, plant.name, geojson_str=geojson_str
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        pdf_url = request.build_absolute_uri(
            settings.MEDIA_URL + "reports/" + os.path.basename(pdf_path)
        )

        return Response({"pdf": pdf_url, "metadata": metadata})
