import ezdxf
import json
from shapely.geometry import Polygon, MultiLineString
from collections import defaultdict


def parse_dxf_to_geojson(dxf_path):
    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()

        # Para armazenar pontos do contorno
        points = []

        # Para coleta de layers
        layer_count = defaultdict(int)

        # Coletar todas as LINEs do DXF
        for line in msp.query("LINE"):
            start = line.dxf.start
            end = line.dxf.end

            # Guardar pontos
            points.append((start.x, start.y))

            # Contagem por layer
            layer_count[line.dxf.layer] += 1

        if len(points) < 3:
            raise ValueError("Não foi possível extrair o polígono do DXF.")

        # Criar polígono
        polygon = Polygon(points)

        # GeoJSON do polígono
        geojson = json.dumps(polygon.__geo_interface__)

        # Metadados
        metadata = {
            "vertices": len(points),
            "total_area": polygon.area,
            "total_perimeter": polygon.length,
            "layers": list(layer_count.keys()),
            "entities_per_layer": dict(layer_count),
        }

        return geojson, metadata

    except Exception as e:
        raise Exception(f"Erro ao processar DXF: {e}")
