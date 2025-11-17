import os
import json

from rest_framework import viewsets
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from django.conf import settings
from shapely.geometry import shape

from .models import Plant
from .serializers import PlantSerializer
from .dxf_parser import parse_dxf_to_geojson
from .report import generate_report_pdf


class PlantViewSet(viewsets.ModelViewSet):
    queryset = Plant.objects.all()
    serializer_class = PlantSerializer

    # ---------------------------
    # GET /plants/{id}/coordinates/
    # ---------------------------
    @action(detail=True, methods=["get"])
    def coordinates(self, request, pk=None):
        plant = self.get_object()
        try:
            geojson_str, metadata = parse_dxf_to_geojson(plant.arquivo_dxf.path)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"geojson": json.loads(geojson_str), "metadata": metadata})

    # ---------------------------
    # GET /plants/{id}/metrics/
    # ---------------------------
    @action(detail=True, methods=["get"])
    def metrics(self, request, pk=None):
        plant = self.get_object()

        try:
            geojson_str, metadata = parse_dxf_to_geojson(plant.arquivo_dxf.path)
            geojson = json.loads(geojson_str)

            polygon = shape(geojson)

            metadata.update(
                {
                    "area": polygon.area,
                    "perimeter": polygon.length,
                    "vertices": len(polygon.exterior.coords),
                }
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(metadata)

    # ---------------------------
    # NOVO: GET /plants/{id}/calculate/
    # ---------------------------
    @action(detail=True, methods=["get"])
    def calculate(self, request, pk=None):
        plant = self.get_object()

        try:
            geojson_str, metadata = parse_dxf_to_geojson(plant.arquivo_dxf.path)
            geojson = json.loads(geojson_str)

            polygon = shape(geojson)

            result = {
                "area": polygon.area,
                "perimeter": polygon.length,
                "vertices": len(polygon.exterior.coords),
                "metadata": metadata,
            }

        except Exception as e:
            return Response({"error": str(e)}, status=400)

        return Response(result)

    # ---------------------------
    # GET /plants/{id}/report/
    # ---------------------------
    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        plant = self.get_object()

        try:
            # DXF → GeoJSON
            geojson_str, metadata = parse_dxf_to_geojson(plant.arquivo_dxf.path)
            geojson = json.loads(geojson_str)

            # Converter para Polygon
            polygon = shape(geojson)

            # Métricas
            metadata.update(
                {
                    "area_m2": round(polygon.area, 3),
                    "perimeter_m": round(polygon.length, 3),
                    "vertices": len(polygon.exterior.coords),
                }
            )

            # Gera PDF com miniatura
            pdf_path = generate_report_pdf(
                metadata, plant.nome, geojson_str=geojson_str  # ← ESSENCIAL
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # URL pública
        pdf_url = request.build_absolute_uri(
            settings.MEDIA_URL + "reports/" + os.path.basename(pdf_path)
        )

        return Response({"pdf": pdf_url, "metadata": metadata})
