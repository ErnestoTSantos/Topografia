import ezdxf
import json
import math
import alphashape

from shapely.geometry import LineString, MultiLineString, mapping, Polygon
from shapely.ops import unary_union, polygonize
from collections import defaultdict


def bulge_to_arc(start, end, bulge, segments=12):
    """Converts a polyline segment with 'bulge' into a series of LineString points."""
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

    d_sq = abs(r**2 - (chord / 2) ** 2)
    d = math.sqrt(d_sq)

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


def arc_to_linestring(arc, segments=12):
    """Converts an ezdxf.Arc entity to a LineString."""
    try:
        points = list(arc.flattening(segments))
        if len(points) >= 2:
            return LineString([(p.x, p.y) for p in points])
    except Exception:
        return None
    return None


def circle_to_linestring(circle, segments=32):
    """Converts an ezdxf.Circle entity to a closed LineString."""
    try:
        center_x, center_y, center_z = circle.dxf.center
        radius = circle.dxf.radius

        pts = []
        for i in range(segments + 1):
            angle = 2 * math.pi * i / segments
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            pts.append((x, y))

        if len(pts) > 1 and pts[0] != pts[-1]:
            pts.append(pts[0])

        return LineString(pts)

    except Exception:
        return None


def parse_hatch_to_polygons(hatch_entity):
    """Extracts polygons from the boundaries (paths) of a HATCH entity."""
    polygons = []
    try:
        for path in hatch_entity.paths:
            if path.path_type in (
                ezdxf.path.BoundaryPathType.POLYLINE,
                ezdxf.path.BoundaryPathType.EDGE_PATH,
            ):
                points = list(path.vertices)
                if len(points) > 2:
                    if path.is_closed and points[0] != points[-1]:
                        points.append(points[0])

                    try:
                        polygons.append(Polygon(points))
                    except Exception:
                        pass
    except Exception:
        pass
    return polygons


def parse_text_to_point(text_entity):
    """Converts TEXT and MTEXT entities into a GeoJSON Point feature."""
    x, y, z = (0, 0, 0)
    text = ""

    if text_entity.dxftype() == "TEXT":
        x, y, z = text_entity.dxf.insert
        text = text_entity.dxf.text
    elif text_entity.dxftype() == "MTEXT":
        x, y, z = text_entity.dxf.insert
        text = text_entity.dxf.text

    if text:
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [x, y, z]},
            "properties": {
                "layer": text_entity.dxf.layer,
                "type": text_entity.dxftype(),
                "text": text,
                "height": (
                    float(text_entity.dxf.char_height)
                    if hasattr(text_entity.dxf, "char_height")
                    else None
                ),
            },
        }
    return None


def get_entities_from_modelspace_and_blocks(msp, doc, target_layers=None):
    """
    Collects supported entities from Modelspace, including those inside block references (INSERT),
    and filters them by the target layers.
    """
    normalized_target_layers = None
    if target_layers is not None:
        if isinstance(target_layers, str):
            target_layers = {target_layers}
        elif isinstance(target_layers, (list, tuple)):
            target_layers = set(target_layers)
        normalized_target_layers = {layer.upper() for layer in target_layers}

    def should_include_in_filter(entity):
        if normalized_target_layers is None:
            return True
        if hasattr(entity, "dxf") and hasattr(entity.dxf, "layer"):
            return entity.dxf.layer.upper() in normalized_target_layers
        return False

    all_raw_entities = []
    supported_types = [
        "LINE",
        "LWPOLYLINE",
        "POLYLINE",
        "ARC",
        "CIRCLE",
        "ELLIPSE",
        "SPLINE",
        "TEXT",
        "MTEXT",
        "HATCH",
        "POINT",
    ]

    for e in msp:
        if e.dxftype() in supported_types:
            all_raw_entities.append(e)

        elif e.dxftype() == "INSERT":
            block_name = e.dxf.name

            try:
                block = doc.blocks.get(block_name)

                for ve in block.virtual_entities(e):
                    if ve.dxftype() in supported_types:
                        all_raw_entities.append(ve)
            except Exception:
                continue

    filtered_entities = []
    for entity in all_raw_entities:
        if normalized_target_layers is None or should_include_in_filter(entity):
            filtered_entities.append(entity)

    return filtered_entities


def parse_dxf_to_geojson(dxf_path, scale_factor=1.0, target_layers=None):
    """
    Processes a DXF file, filters by layers, explodes blocks, and calculates totals.
    """

    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()

        lines = []
        features_non_geometry = []

        layer_count = defaultdict(int)
        original_drawing_entities = []

        entities_to_process = get_entities_from_modelspace_and_blocks(
            msp, doc, target_layers
        )

        for e in entities_to_process:
            layer_count[e.dxf.layer] += 1
            geometry_obj = None

            if e.dxftype() in [
                "LINE",
                "ARC",
                "CIRCLE",
                "ELLIPSE",
                "SPLINE",
                "POLYLINE",
                "LWPOLYLINE",
            ]:
                if e.dxftype() == "LINE":
                    start = (e.dxf.start.x, e.dxf.start.y)
                    end = (e.dxf.end.x, e.dxf.end.y)
                    geometry_obj = LineString([start, end])

                elif e.dxftype() == "LWPOLYLINE":
                    pts = []
                    bulges = []
                    for p in e:
                        try:
                            x, y = p[0], p[1]
                            bulge = (
                                p.bulge
                                if hasattr(p, "bulge")
                                else (
                                    p[4]
                                    if isinstance(p, (list, tuple)) and len(p) >= 5
                                    else 0
                                )
                            )
                            pts.append((x, y))
                            bulges.append(bulge)
                        except Exception:
                            continue

                    if len(pts) >= 2:
                        new_pts = []
                        for i in range(len(pts) - 1):
                            new_pts.extend(bulge_to_arc(pts[i], pts[i + 1], bulges[i]))

                        if e.closed:
                            new_pts.extend(bulge_to_arc(pts[-1], pts[0], bulges[-1]))

                        try:
                            geometry_obj = LineString(new_pts)
                        except Exception:
                            pass

                elif e.dxftype() == "POLYLINE":
                    pts = []
                    for v in e.vertices:
                        try:
                            pts.append(
                                (float(v.dxf.location.x), float(v.dxf.location.y))
                            )
                        except Exception:
                            continue
                    if len(pts) >= 2:
                        geometry_obj = LineString(pts)

                elif e.dxftype() == "ARC":
                    geometry_obj = arc_to_linestring(e)

                elif e.dxftype() == "CIRCLE":
                    geometry_obj = circle_to_linestring(e)

                elif e.dxftype() == "ELLIPSE" or e.dxftype() == "SPLINE":
                    try:
                        points = list(e.flattening(12))
                        geometry_obj = LineString([(p.x, p.y) for p in points])
                    except Exception:
                        pass

                if geometry_obj and not geometry_obj.is_empty:
                    lines.append(geometry_obj)
                    original_drawing_entities.append(
                        {
                            "geometry": geometry_obj,
                            "layer": e.dxf.layer,
                            "type": e.dxftype(),
                        }
                    )

            elif e.dxftype() == "HATCH":
                polygons_hatch = parse_hatch_to_polygons(e)
                for poly in polygons_hatch:
                    if poly.is_valid and not poly.is_empty:
                        original_drawing_entities.append(
                            {
                                "geometry": poly,
                                "layer": e.dxf.layer,
                                "type": e.dxftype(),
                            }
                        )

            elif e.dxftype() in ["TEXT", "MTEXT"]:
                text_feature = parse_text_to_point(e)
                if text_feature:
                    features_non_geometry.append(text_feature)

            elif e.dxftype() == "POINT":
                try:
                    x, y, z = e.dxf.location

                    point_feature = {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [x, y, z]},
                        "properties": {
                            "layer": e.dxf.layer,
                            "type": e.dxftype(),
                        },
                    }
                    features_non_geometry.append(point_feature)
                except Exception:
                    pass

        if len(lines) == 0 and len(features_non_geometry) == 0:
            all_layers = list(doc.layers)
            layer_names = [layer.dxf.name for layer in all_layers]

            error_message = f"No supported geometric entities found in the file."
            if target_layers is not None:
                error_message = f"No entities found in the selected layers. Available layers: {layer_names}"

            raise ValueError(error_message)

        polygons = []
        if len(lines) > 0:
            merged_lines = unary_union(lines)

            if merged_lines.geom_type in ("LineString", "MultiLineString"):
                try:
                    polygons = list(polygonize(merged_lines))
                except Exception:
                    polygons = []

            if len(polygons) == 0:
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

        features = []
        constructions = []
        total_area = 0.0
        total_perimeter = 0.0

        for poly in polygons:
            if poly.is_valid and not poly.is_empty:
                area = float(poly.area) * (scale_factor**2)
                perimeter = float(poly.length) * scale_factor

                total_area += area
                total_perimeter += perimeter

                data = {
                    "area": area,
                    "perimeter": perimeter,
                    "vertices": len(list(poly.exterior.coords)),
                }
                constructions.append(data)
                features.append(
                    {"type": "Feature", "properties": data, "geometry": mapping(poly)}
                )

        features.extend(features_non_geometry)
        geojson_fc = {"type": "FeatureCollection", "features": features}

        metadata = {
            "constructions": constructions,
            "total_constructions": len(constructions),
            "entities_per_layer": dict(layer_count),
            "layers": list(layer_count.keys()),
            "total_area_m2": total_area,
            "total_perimeter_m": total_perimeter,
            "total_entities_found": len(original_drawing_entities)
            + len(features_non_geometry),
        }

        if target_layers is None:
            all_features_no_filter = []
            for item in original_drawing_entities:
                all_features_no_filter.append(
                    {
                        "type": "Feature",
                        "geometry": mapping(item["geometry"]),
                        "properties": {"layer": item["layer"], "type": item["type"]},
                    }
                )
            all_features_no_filter.extend(features_non_geometry)
            geojson_fc_no_filter = {
                "type": "FeatureCollection",
                "features": all_features_no_filter,
            }

            return json.dumps(geojson_fc_no_filter), metadata, original_drawing_entities

        return json.dumps(geojson_fc), metadata, polygons

    except ValueError as e:
        raise
    except Exception as e:
        raise Exception(f"Error processing DXF: {e}")
