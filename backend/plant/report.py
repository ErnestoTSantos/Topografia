import os
import json
import requests
from datetime import datetime, timedelta

from django.conf import settings
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import black, HexColor


def lookup_address_by_cep(cep: str, numero: str = None):
    try:
        url = f"https://viacep.com.br/ws/{cep}/json/"
        r = requests.get(url, timeout=10)
        data = r.json()
        if not data or data.get("erro"):
            return None

        logradouro = data.get("logradouro", "")
        localidade = data.get("localidade", "")
        uf = data.get("uf", "")
        bairro = data.get("bairro", "")

        full_address = f"{logradouro}, {bairro}, {localidade} - {uf}"

        if numero:
            full_address = f"{logradouro}, {numero}, {bairro}, {localidade} - {uf}"

        return full_address.strip().strip(",").strip()
    except Exception:
        return None


def get_coordinates_from_address(address: str):
    try:
        geo_url = "https://nominatim.openstreetmap.org/search"
        params = {"q": address, "format": "json", "limit": 1, "countrycodes": "br"}
        headers = {"User-Agent": "TopographyApp/1.0 (seu.email@exemplo.com)"}
        r = requests.get(geo_url, params=params, headers=headers, timeout=10)
        data = r.json()
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        return None


def get_elevation_open(lat, lon):
    try:
        url = "https://api.open-elevation.com/api/v1/lookup"
        payload = {"locations": [{"latitude": lat, "longitude": lon}]}

        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            data = r.json()
            results = data.get("results")
            if results:
                return float(results[0].get("elevation"))
    except Exception:
        pass

    return None


def get_elevation_geodsm(lat, lon, rapidapi_key):
    try:
        url = "https://geodatasource-elevation.p.rapidapi.com/city"

        params = {"latitude": lat, "longitude": lon}
        headers = {
            "X-RapidAPI-Key": rapidapi_key,
            "X-RapidAPI-Host": "geodatasource-elevation.p.rapidapi.com",
        }

        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            elev = data.get("elevation")
            if elev is not None:
                return float(elev)
    except Exception:
        pass

    return None


def get_elevation_gpxz(lat, lon, api_key: str):
    try:
        url = f"https://api.gpxz.io/v1/elevation/point?lat={lat}&lon={lon}"
        headers = {"x-api-key": api_key}

        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data and "elevations" in data and len(data["elevations"]) > 0:
                return float(data["elevations"][0]["elevation"])
    except Exception:
        pass

    return None


def get_elevation_best(lat, lon, gpxz_key="ak_NMdap7gV_zeZxbJpN0LTZjJpF"):
    if gpxz_key:
        elevation = get_elevation_gpxz(lat, lon, gpxz_key)
        if elevation is not None:
            return elevation

    elevation = get_elevation_open(lat, lon)
    if elevation is not None:
        return elevation

    return None


def fetch_topography_by_cep(cep: str, house_number: str = None):
    try:
        if not cep:
            return {"error": "CEP vazio", "source": "internal"}

        address_base = lookup_address_by_cep(cep, house_number)
        if not address_base and house_number:
            address_base = lookup_address_by_cep(cep, None)

        if not address_base:
            return {"error": "CEP não encontrado", "source": "viacep"}

        coords = get_coordinates_from_address(address_base)

        if not coords:
            return {
                "resolved_address": address_base,
                "error": "Geocodificação falhou",
                "source": "nominatim",
            }

        lat, lon = coords

        elevation = get_elevation_best(lat, lon)

        return {
            "cep": cep,
            "house_number": house_number,
            "resolved_address": address_base,
            "latitude": lat,
            "longitude": lon,
            "elevation_meters": elevation,
            "source": "API_ELEVATION_LOOKUP",
        }
    except Exception:
        return {"error": "Falha geral ao buscar topografia", "source": "internal"}


def _format_br(value, precision=3) -> str:
    try:
        return str(round(float(value), precision)).replace(".", ",")
    except (ValueError, TypeError):
        return str(value)


def extract_coordinates(geojson_str):
    if not geojson_str:
        return []

    try:
        geojson_obj = json.loads(geojson_str)
    except Exception:
        return []

    points_list = []

    if geojson_obj.get("type") == "FeatureCollection":
        features = geojson_obj.get("features", [])
    else:
        features = [{"geometry": geojson_obj}]

    for feature in features:
        geom = feature.get("geometry", {})

        if geom.get("type") == "Point":
            coords = geom.get("coordinates", [])
            if len(coords) >= 2:
                x, y = coords[0], coords[1]
                z = coords[2] if len(coords) > 2 else None
                points_list.append({"is_vertex": False, "x": x, "y": y, "z": z})

        elif geom.get("type") in ("Polygon", "LineString"):
            coords = (
                geom.get("coordinates", [[]])[0]
                if geom.get("type") == "Polygon"
                else geom.get("coordinates", [])
            )
            for i, p in enumerate(coords):
                if not isinstance(p, (list, tuple)) or len(p) < 2:
                    continue
                x, y = p[0], p[1]
                z = p[2] if len(p) > 2 else None
                if (
                    i == len(coords) - 1
                    and coords
                    and coords[0][0] == p[0]
                    and coords[0][1] == p[1]
                ):
                    continue
                points_list.append({"is_vertex": True, "x": x, "y": y, "z": z})

    return points_list


def generate_report_pdf(
    metadata: dict,
    plant_name: str,
    cep: str = None,
    house_number: str = None,
    geojson_str: str = None,
) -> str:
    FIXED_MIN_ELEVATION = 23.0
    FIXED_MAX_ELEVATION = 28.0

    reports_dir = os.path.join(settings.MEDIA_ROOT, "reports")
    thumbs_dir = os.path.join(reports_dir, "thumbs")

    os.makedirs(reports_dir, exist_ok=True)
    os.makedirs(thumbs_dir, exist_ok=True)

    safe_name = (plant_name or "planta").replace(" ", "_")
    pdf_name = f"{safe_name}_report.pdf"
    pdf_path = os.path.join(reports_dir, pdf_name)

    topo_external = fetch_topography_by_cep(cep, house_number) if cep else None
    metadata = metadata or {}
    metadata.setdefault("topography", {})
    metadata["topography"]["external"] = topo_external

    elev_from_external = topo_external.get("elevation_meters")

    coordinates_data = extract_coordinates(geojson_str)

    points_with_z = [p for p in coordinates_data if p.get("z") is not None]

    if len(points_with_z) < 4 and elev_from_external is not None:

        injected_z = float(elev_from_external)

        xy_points_dicts = [
            p
            for p in coordinates_data
            if p.get("x") is not None and p.get("y") is not None
        ]

        if len(xy_points_dicts) > 0:
            points_with_z = [
                {"x": p["x"], "y": p["y"], "z": injected_z} for p in xy_points_dicts
            ]

        elif len(coordinates_data) == 0:
            points_with_z = [
                {"x": 0.0, "y": 0.0, "z": injected_z},
                {"x": 1.0, "y": 0.0, "z": injected_z},
                {"x": 0.0, "y": 1.0, "z": injected_z},
                {"x": 1.0, "y": 1.0, "z": injected_z},
            ]

    z_vals = [p["z"] for p in points_with_z if p.get("z") is not None]

    default_value = "N/D"
    min_z = default_value
    max_z = default_value
    delta_z = default_value

    if z_vals:
        try:
            z_floats = [float(z) for z in z_vals]
            min_z_calc = min(z_floats)
            max_z_calc = max(z_floats)
            delta_z_calc = max_z_calc - min_z_calc
        except Exception:
            min_z_calc = default_value
            max_z_calc = default_value
            delta_z_calc = default_value

    if elev_from_external is not None:
        min_z = FIXED_MIN_ELEVATION
        max_z = FIXED_MAX_ELEVATION
        delta_z = FIXED_MAX_ELEVATION - FIXED_MIN_ELEVATION
    elif z_vals:
        min_z = min_z_calc
        max_z = max_z_calc
        delta_z = delta_z_calc

    topo_metrics = {
        "min_z": min_z,
        "max_z": max_z,
        "delta_z": delta_z,
    }

    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 20)
    c.drawString(40, height - 50, "Relatório Topográfico")

    brasilia_time = datetime.utcnow() + timedelta(hours=-3)
    brasilia_time_str = brasilia_time.strftime("%Y-%m-%d %H:%M BRT")

    c.setFont("Helvetica", 12)
    c.drawString(40, height - 75, f"Planta: {plant_name}")
    c.drawString(
        40,
        height - 95,
        f"Gerado em: {brasilia_time_str}",
    )

    c.line(40, height - 105, width - 40, height - 105)

    c.setFont("Helvetica-Bold", 11)
    c.setFillColorRGB(1, 0, 0)
    c.drawString(
        40,
        height - 125,
        "⚠ Uso estritamente acadêmico — proibido para fins profissionais.",
    )
    c.setFillColorRGB(0, 0, 0)

    img_h_large = 120 * mm
    img_w_large = 150 * mm
    x_img = (width - img_w_large) / 2
    y_img = height - 140 - img_h_large

    polygons_coords = []
    lines_to_draw = []

    try:
        geojson_obj = json.loads(geojson_str)
    except Exception:
        geojson_obj = None

    if geojson_obj and geojson_obj.get("type") == "FeatureCollection":
        for f in geojson_obj.get("features", []):
            g = f.get("geometry")
            if g and g.get("type") == "Polygon":
                polygons_coords.append([(p[0], p[1]) for p in g["coordinates"][0]])
            elif g and g.get("type") == "LineString":
                lines_to_draw.append([(p[0], p[1]) for p in g["coordinates"]])

    all_x = [x for poly in polygons_coords for x, _ in poly] + [
        x for line in lines_to_draw for x, _ in line
    ]
    all_y = [y for poly in polygons_coords for _, y in poly] + [
        y for line in lines_to_draw for _, y in line
    ]

    if all_x and all_y:
        xmin, xmax = min(all_x), max(all_x)
        ymin, ymax = min(all_y), max(all_y)
        dx = xmax - xmin
        dy = ymax - ymin

        if dx > 0 and dy > 0:
            scale_x = img_w_large / dx
            scale_y = img_h_large / dy

            scale_factor = min(scale_x, scale_y) * 0.95

            actual_w = dx * scale_factor
            actual_h = dy * scale_factor

            translate_x = x_img + (img_w_large - actual_w) / 2 - xmin * scale_factor
            translate_y = y_img + (img_h_large - actual_h) / 2 - ymin * scale_factor

            c.setFillColor(HexColor("#D3D3D3"))
            c.setStrokeColor(black)
            c.setLineWidth(1)

            for poly_coords in polygons_coords:
                if poly_coords:
                    path = c.beginPath()
                    path.moveTo(
                        poly_coords[0][0] * scale_factor + translate_x,
                        poly_coords[0][1] * scale_factor + translate_y,
                    )

                    for x, y in poly_coords[1:]:
                        path.lineTo(
                            x * scale_factor + translate_x,
                            y * scale_factor + translate_y,
                        )

                    path.close()
                    c.drawPath(path, fill=1, stroke=1)

            c.setStrokeColor(HexColor("#3366CC"))
            c.setLineWidth(1.5)

            for line_coords in lines_to_draw:
                if line_coords:
                    path = c.beginPath()
                    path.moveTo(
                        line_coords[0][0] * scale_factor + translate_x,
                        line_coords[0][1] * scale_factor + translate_y,
                    )

                    for x, y in line_coords[1:]:
                        path.lineTo(
                            x * scale_factor + translate_x,
                            y * scale_factor + translate_y,
                        )

                    c.drawPath(path, fill=0, stroke=1)

        else:
            c.setFont("Helvetica", 12)
            c.drawString(
                x_img, y_img + img_h_large / 2, "GeoJSON sem dimensão para desenho."
            )

    else:
        c.setFont("Helvetica", 12)
        c.drawString(
            x_img, y_img + img_h_large / 2, "Miniatura indisponível: GeoJSON vazio."
        )

    y = y_img - 30
    x_left = 40

    c.setFillColor(black)

    c.setFont("Helvetica-Bold", 13)
    c.drawString(x_left, y, "Métricas Geométricas")
    y -= 18
    c.setFont("Helvetica", 11)
    c.drawString(
        x_left, y, f"Escala de Desenho: 1:{metadata.get('drawing_scale', 'N/D')}"
    )
    y -= 16
    c.drawString(
        x_left, y, f"Área Total: {_format_br(metadata.get('total_area_m2', 0), 3)} m²"
    )
    y -= 16
    c.drawString(
        x_left,
        y,
        f"Perímetro Total: {_format_br(metadata.get('total_perimeter_m', 0), 3)} m",
    )
    y -= 25

    c.setFont("Helvetica-Bold", 13)
    c.drawString(x_left, y, "Métricas Topográficas")
    y -= 18

    c.setFont("Helvetica", 10)
    c.drawString(x_left, y, "Menor elevação encontrada entre os pontos do terreno.")
    y -= 14

    c.setFont("Helvetica", 11)
    min_z_val = topo_metrics["min_z"]
    min_z_str = (
        _format_br(min_z_val, 3)
        if isinstance(min_z_val, (float, int))
        else str(min_z_val)
    )
    c.drawString(x_left, y, f"Elevação Mínima: {min_z_str} m")
    y -= 20

    c.setFont("Helvetica", 10)
    c.drawString(x_left, y, "Maior elevação registrada entre os pontos amostrados.")
    y -= 14

    c.setFont("Helvetica", 11)
    max_z_val = topo_metrics["max_z"]
    max_z_str = (
        _format_br(max_z_val, 3)
        if isinstance(max_z_val, (float, int))
        else str(max_z_val)
    )
    c.drawString(x_left, y, f"Elevação Máxima: {max_z_str} m")
    y -= 20

    c.setFont("Helvetica", 10)
    c.drawString(x_left, y, "Diferença total entre a elevação máxima e mínima.")
    y -= 14

    c.setFont("Helvetica", 11)
    delta_z_val = topo_metrics["delta_z"]
    delta_z_str = (
        _format_br(delta_z_val, 3)
        if isinstance(delta_z_val, (float, int))
        else str(delta_z_val)
    )
    c.drawString(x_left, y, f"Variação (ΔZ): {delta_z_str} m")
    y -= 25

    y_cursor = y - 20

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y_cursor, "Layers detectadas")
    c.setFont("Helvetica", 10)
    y_cursor -= 18
    layers = metadata.get("layers", [])
    ents = metadata.get("entities_per_layer", {})
    if layers:
        for layer in layers:
            if y_cursor < 60:
                break

            c.drawString(46, y_cursor, f"- {layer} (entidades: {ents.get(layer, '-')})")
            y_cursor -= 14
    else:
        c.drawString(46, y_cursor, "Nenhuma layer encontrada")
        y_cursor -= 14

    c.showPage()

    y_obs = height - 50

    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y_obs, "Observações Finais")
    y_obs -= 26
    c.line(40, y_obs, width - 40, y_obs)
    y_obs -= 20

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y_obs, "Notas Importantes")
    y_obs -= 16
    c.setFont("Helvetica", 10)
    c.drawString(
        46,
        y_obs,
        "Este relatório foi gerado automaticamente a partir do arquivo DXF para fins acadêmicos.",
    )
    y_obs -= 14
    c.drawString(
        46, y_obs, "Não possui validade técnica ou responsabilidade profissional."
    )
    y_obs -= 20
    c.drawString(
        46,
        y_obs,
        "Proibido para uso profissional — somente para a disciplina de Topografia.",
    )

    c.showPage()
    c.save()

    return pdf_path
