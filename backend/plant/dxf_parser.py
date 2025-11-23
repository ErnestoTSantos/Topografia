import ezdxf
import json
import math
import alphashape

from shapely.geometry import LineString, MultiLineString, mapping
from shapely.ops import unary_union, polygonize
from collections import defaultdict


def bulge_to_arc(start, end, bulge, segments=12):
    if bulge == 0:
        return [start, end]

    x1, y1 = start
    x2, y2 = end

    dx = x2 - x1
    dy = y2 - y1
    chord = math.hypot(dx, dy)

    if chord == 0:
        return [start]

    theta = 4 * math.atan(abs(bulge))
    r = chord / (2 * math.sin(theta / 2))

    mx = (x1 + x2) / 2
    my = (y1 + y2) / 2

    d = math.sqrt(abs(r**2 - (chord / 2) ** 2))

    ux = -dy / chord
    uy = dx / chord

    if bulge < 0:
        ux, uy = -ux, -uy

    cx = mx + ux * d
    cy = my + uy * d

    a1 = math.atan2(y1 - cy, x1 - cx)
    a2 = math.atan2(y2 - cy, x2 - cx)

    if bulge > 0 and a2 < a1:
        a2 += 2 * math.pi
    elif bulge < 0 and a2 > a1:
        a2 -= 2 * math.pi

    pts = []
    for i in range(segments + 1):
        t = a1 + (a2 - a1) * i / segments
        pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))

    return pts


def parse_dxf_to_geojson(dxf_path, scale_factor=1.0, target_layers=None):
    """
    Processa um arquivo DXF para GeoJSON, aplicando fator de escala
    e filtrando entidades por layer alvo.
    """

    if target_layers is not None:
        if isinstance(target_layers, str):
            target_layers = {target_layers}
        elif isinstance(target_layers, (list, tuple)):
            target_layers = set(target_layers)
        else:
            target_layers = None

    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()

        lines = []
        layer_count = defaultdict(int)

        original_drawing_entities = []

        def should_include(entity):
            layer = entity.dxf.layer
            layer_count[layer] += 1

            if target_layers is None:
                return True
            return layer in target_layers

        for e in msp.query("LINE"):
            is_included = should_include(e)
            if not is_included and target_layers is not None:
                continue

            start = (e.dxf.start.x, e.dxf.start.y)
            end = (e.dxf.end.x, e.dxf.end.y)
            line = LineString([start, end])
            if not line.is_empty:
                if is_included or target_layers is None:
                    lines.append(line)
                original_drawing_entities.append(line)

        for e in msp.query("LWPOLYLINE"):
            is_included = should_include(e)
            if not is_included and target_layers is not None:
                continue

            pts = []
            bulges = []

            for p in e:
                try:
                    x, y = p[0], p[1]
                except Exception:
                    continue

                bulge = 0
                if hasattr(p, "bulge"):
                    bulge = p.bulge
                elif isinstance(p, (list, tuple)) and len(p) >= 5:
                    bulge = p[4]

                pts.append((x, y))
                bulges.append(bulge)

            if len(pts) < 2:
                continue

            new_pts = []
            for i in range(len(pts) - 1):
                new_pts.extend(bulge_to_arc(pts[i], pts[i + 1], bulges[i]))

            if e.closed:
                new_pts.extend(bulge_to_arc(pts[-1], pts[0], bulges[-1]))

            if len(new_pts) >= 2:
                try:
                    line_string = LineString(new_pts)
                    if is_included or target_layers is None:
                        lines.append(line_string)
                    original_drawing_entities.append(line_string)
                except Exception:
                    pass

        for e in msp.query("POLYLINE"):
            is_included = should_include(e)
            if not is_included and target_layers is not None:
                continue

            pts = []
            for v in e.vertices:
                try:
                    pts.append((float(v.dxf.location.x), float(v.dxf.location.y)))
                except Exception:
                    continue

            if len(pts) >= 2:
                line_string = LineString(pts)
                if is_included or target_layers is None:
                    lines.append(line_string)
                original_drawing_entities.append(line_string)

        if len(lines) == 0:
            raise ValueError(
                "Nenhuma entidade de linha/polilinha encontrada nos layers selecionados."
            )

        merged_lines = unary_union(lines)

        polygons = []
        if target_layers is not None:
            if merged_lines.geom_type in ("LineString", "MultiLineString"):
                try:
                    polygons = list(polygonize(merged_lines))
                except Exception:
                    polygons = []
            else:
                polygons = []

        if len(polygons) == 0 and target_layers is not None:
            all_pts = []

            for l in lines:
                all_pts.extend(list(l.coords))

            try:
                outline = alphashape.alphashape(all_pts, 0.01)

                if outline.geom_type == "Polygon":
                    polygons = [outline]
                elif outline.geom_type == "MultiPolygon":
                    polygons.extend(list(outline.geoms))

            except Exception:
                pass

        if len(polygons) == 0 and target_layers is not None:
            raise ValueError("Nenhuma construção pôde ser identificada.")

        features = []
        constructions = []
        if target_layers is not None and len(polygons) > 0:
            for poly in polygons:
                if poly.is_valid and not poly.is_empty:
                    data = {
                        "area": float(poly.area) * (scale_factor**2),
                        "perimeter": float(poly.length) * scale_factor,
                        "vertices": len(list(poly.exterior.coords)),
                    }
                    constructions.append(data)
                    features.append(
                        {
                            "type": "Feature",
                            "properties": data,
                            "geometry": mapping(poly),
                        }
                    )

        metadata = {
            "constructions": constructions,
            "total_constructions": len(constructions),
            "entities_per_layer": dict(layer_count),
            "layers": list(layer_count.keys()),
        }

        if target_layers is None:
            geojson_fc = {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "geometry": mapping(l)}
                    for l in original_drawing_entities
                ],
            }
            return json.dumps(geojson_fc), metadata, original_drawing_entities
        return (
            json.dumps({"type": "FeatureCollection", "features": features}),
            metadata,
            polygons,
        )

    except Exception as e:
        raise Exception(f"Erro ao processar DXF: {e}")
