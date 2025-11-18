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


def parse_dxf_to_geojson(dxf_path):
    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()

        lines = []
        layer_count = defaultdict(int)

        for e in msp.query("LINE"):
            start = (e.dxf.start.x, e.dxf.start.y)
            end = (e.dxf.end.x, e.dxf.end.y)
            line = LineString([start, end])
            if not line.is_empty:
                lines.append(line)
            layer_count[e.dxf.layer] += 1

        for e in msp.query("LWPOLYLINE"):
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
                    lines.append(LineString(new_pts))
                except Exception:
                    pass

            layer_count[e.dxf.layer] += 1

        for e in msp.query("POLYLINE"):
            pts = []
            for v in e.vertices:
                try:
                    pts.append((float(v.dxf.location.x), float(v.dxf.location.y)))
                except Exception:
                    continue

            if len(pts) >= 2:
                lines.append(LineString(pts))
            layer_count[e.dxf.layer] += 1

        if len(lines) == 0:
            raise ValueError("Nenhuma entidade de linha/polilinha encontrada no DXF.")

        mls = MultiLineString(lines)

        polygons = list(polygonize(mls))

        if len(polygons) == 0:
            all_pts = []
            for l in lines:
                all_pts.extend(list(l.coords))

            outline = alphashape.alphashape(all_pts, 0.01)
            if outline.geom_type == "Polygon":
                polygons = [outline]

        if len(polygons) == 0:
            raise ValueError("Nenhuma construção pôde ser identificada.")

        features = []
        constructions = []

        for poly in polygons:
            data = {
                "area": float(poly.area),
                "perimeter": float(poly.length),
                "vertices": len(list(poly.exterior.coords)),
            }

            constructions.append(data)

            features.append(
                {"type": "Feature", "properties": data, "geometry": mapping(poly)}
            )

        geojson_fc = {"type": "FeatureCollection", "features": features}

        metadata = {
            "constructions": constructions,
            "total_constructions": len(constructions),
            "entities_per_layer": dict(layer_count),
            "layers": list(layer_count.keys()),
        }

        return json.dumps(geojson_fc), metadata, polygons

    except Exception as e:
        raise Exception(f"Erro ao processar DXF: {e}")
