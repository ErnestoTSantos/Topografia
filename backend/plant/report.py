import os
import json
from datetime import datetime

from django.conf import settings
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

import matplotlib
import matplotlib.pyplot as plt

matplotlib.use("Agg")


def _make_thumbnail_from_geojson(geojson_obj, out_path, width_px=800, height_px=600):
    """Gera PNG com miniatura da planta. Ajustado para desenhar Polígonos E Linhas Soltas."""
    if isinstance(geojson_obj, str):
        geojson_obj = json.loads(geojson_obj)

    polygons = []
    lines_to_draw = []

    # Tratar LineString (linhas soltas) e Polygon
    if geojson_obj.get("type") == "FeatureCollection":
        for f in geojson_obj.get("features", []):
            g = f.get("geometry")
            if g and g.get("type") == "Polygon":
                polygons.append(g["coordinates"][0])
            elif g and g.get("type") == "LineString":
                lines_to_draw.append(g["coordinates"])

    if not polygons and not lines_to_draw:
        fig = plt.figure(figsize=(width_px / 100, height_px / 100), dpi=100)
        plt.text(0.5, 0.5, "Miniatura indisponível", ha="center", va="center")
        plt.axis("off")
        fig.savefig(out_path, bbox_inches="tight", pad_inches=0.2)
        plt.close(fig)
        return out_path

    fig, ax = plt.subplots(figsize=(width_px / 100, height_px / 100), dpi=100)

    # Fundo Branco
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    # Desenhar os polígonos (para o contorno externo)
    for poly in polygons:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        ax.plot(xs, ys, linewidth=1.5, color="black")

    # Desenhar as linhas soltas (para os detalhes internos)
    for line_coords in lines_to_draw:
        xs = [p[0] for p in line_coords]
        ys = [p[1] for p in line_coords]
        ax.plot(xs, ys, linewidth=1.0, color="black")

    ax.set_aspect("equal", "box")
    ax.axis("off")

    all_x = [x for poly in polygons for x, _ in poly] + [
        x for line in lines_to_draw for x, _ in line
    ]
    all_y = [y for poly in polygons for _, y in poly] + [
        y for line in lines_to_draw for _, y in line
    ]

    if not all_x or not all_y:
        ax.axis("off")
        fig.savefig(out_path, bbox_inches="tight", pad_inches=0.2)
        plt.close(fig)
        return out_path

    xmin, xmax = min(all_x), max(all_x)
    ymin, ymax = min(all_y), max(all_y)

    dx = xmax - xmin
    dy = ymax - ymin

    max_dim = max(dx, dy) or 1
    pad_factor = 0.15
    center_padding_x = (max_dim - dx) / 2
    center_padding_y = (max_dim - dy) / 2

    final_xmin = xmin - center_padding_x - (max_dim * pad_factor)
    final_xmax = xmax + center_padding_x + (max_dim * pad_factor)
    final_ymin = ymin - center_padding_y - (max_dim * pad_factor)
    final_ymax = ymax + center_padding_y + (max_dim * pad_factor)

    ax.set_xlim(final_xmin, final_xmax)
    ax.set_ylim(final_ymin, final_ymax)

    fig.savefig(out_path, bbox_inches="tight", pad_inches=0)
    plt.close(fig)

    return out_path


def extract_coordinates(geojson_str):
    if not geojson_str:
        return []

    geojson_obj = json.loads(geojson_str)
    points_list = []

    if geojson_obj.get("type") == "FeatureCollection":
        features = geojson_obj.get("features", [])
    else:
        features = [{"geometry": geojson_obj}]

    for idx, feature in enumerate(features):
        geom = feature.get("geometry", {})
        if geom.get("type") in ("Polygon", "LineString"):
            coords = (
                geom["coordinates"][0]
                if geom.get("type") == "Polygon"
                else geom["coordinates"]
            )

            for i, (x, y) in enumerate(coords):
                if i == len(coords) - 1 and x == coords[0][0] and y == coords[0][1]:
                    continue

                points_list.append({"const": idx + 1, "idx": i + 1, "x": x, "y": y})
    return points_list


def generate_report_pdf(
    metadata: dict, plant_name: str, geojson_str: str = None
) -> str:
    """Gera PDF completo com miniatura, métricas, coordenadas e aviso acadêmico."""

    reports_dir = os.path.join(settings.MEDIA_ROOT, "reports")
    thumbs_dir = os.path.join(reports_dir, "thumbs")

    os.makedirs(reports_dir, exist_ok=True)
    os.makedirs(thumbs_dir, exist_ok=True)

    safe_name = (plant_name or "planta").replace(" ", "_")
    pdf_name = f"{safe_name}_report.pdf"
    pdf_path = os.path.join(reports_dir, pdf_name)

    thumb_path = os.path.join(thumbs_dir, f"{safe_name}_thumb.png")

    # gerar miniatura real
    try:
        if geojson_str:
            _make_thumbnail_from_geojson(geojson_str, thumb_path)
        elif metadata.get("geojson"):
            _make_thumbnail_from_geojson(metadata["geojson"], thumb_path)
        else:
            _make_thumbnail_from_geojson({}, thumb_path)
    except Exception:
        _make_thumbnail_from_geojson({}, thumb_path)

    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    y_cursor = height - 105 - 65 * mm - 40

    # ============================================================
    # CABEÇALHO
    # ============================================================
    c.setFont("Helvetica-Bold", 20)
    c.drawString(40, height - 50, "Relatório Topográfico")

    c.setFont("Helvetica", 12)
    c.drawString(40, height - 75, f"Planta: {plant_name}")
    c.drawString(
        40,
        height - 95,
        f"Gerado em: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
    )

    # Linha
    c.line(40, height - 105, width - 40, height - 105)

    # Aviso acadêmico
    c.setFont("Helvetica-Bold", 11)
    c.setFillColorRGB(1, 0, 0)
    c.drawString(
        40,
        height - 125,
        "⚠ Uso estritamente acadêmico — proibido para fins profissionais.",
    )
    c.setFillColorRGB(0, 0, 0)

    # ============================================================
    # MINIATURA
    # ============================================================
    try:
        img = ImageReader(thumb_path)
        img_w = 90 * mm
        img_h = 65 * mm
        c.drawImage(
            img,
            40,
            height - 105 - img_h - 25,
            width=img_w,
            height=img_h,
            preserveAspectRatio=True,
        )
    except Exception:
        pass

    # ============================================================
    # MÉTRICAS (lado direito)
    # ============================================================

    x_right = 40 + (95 * mm)
    y_start = height - 155

    c.setFont("Helvetica-Bold", 13)
    c.drawString(x_right, y_start, "Métricas principais")

    c.setFont("Helvetica", 11)
    y = y_start - 20

    c.drawString(x_right, y, f"Área: {metadata.get('total_area_m2', 0):.3f} m²")
    y -= 16
    c.drawString(x_right, y, f"Perímetro: {metadata.get('total_perimeter_m', 0):.3f} m")
    y -= 16
    c.drawString(x_right, y, f"Vértices: {metadata.get('total_vertices', 0)}")
    y -= 16

    # ============================================================
    # LISTA DE LAYERS
    # ============================================================
    cursor_y = y_cursor

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, cursor_y, "Layers detectadas")
    c.setFont("Helvetica", 10)
    cursor_y -= 18

    layers = metadata.get("layers", [])
    ents = metadata.get("entities_per_layer", {})

    if layers:
        for layer in layers:
            c.drawString(46, cursor_y, f"- {layer} (entidades: {ents.get(layer, '-')})")
            cursor_y -= 14
            if cursor_y < 60:
                c.showPage()
                cursor_y = height - 40
    else:
        c.drawString(46, cursor_y, "Nenhuma layer encontrada")
        cursor_y -= 14

    cursor_y -= 10

    # ============================================================
    # LISTA DE COORDENADAS (AJUSTADO O ESPAÇAMENTO DA TABELA)
    # ============================================================

    coordinates_data = extract_coordinates(geojson_str)

    if coordinates_data:
        # Título
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, cursor_y, "Coordenadas dos Vértices (m)")
        cursor_y -= 18

        # Cabeçalho da Tabela
        col_x = 40
        col_spacing = 50

        c.setFont("Helvetica-Bold", 10)
        c.drawString(col_x, cursor_y, "Const")
        c.drawString(col_x + col_spacing, cursor_y, "Vértice")
        c.drawString(col_x + col_spacing * 2, cursor_y, "X (m)")
        c.drawString(col_x + col_spacing * 4.5, cursor_y, "Y (m)")

        cursor_y -= 12
        c.line(col_x, cursor_y, col_x + col_spacing * 6, cursor_y)
        cursor_y -= 5

        c.setFont("Helvetica", 9)

        for point in coordinates_data:
            if cursor_y < 60:
                c.showPage()
                cursor_y = height - 40

                c.setFont("Helvetica-Bold", 10)
                c.drawString(col_x, cursor_y, "Const")
                c.drawString(col_x + col_spacing, cursor_y, "Vértice")
                c.drawString(col_x + col_spacing * 2, cursor_y, "X (m)")
                c.drawString(col_x + col_spacing * 4.5, cursor_y, "Y (m)")
                cursor_y -= 12
                c.line(col_x, cursor_y, col_x + col_spacing * 6, cursor_y)
                cursor_y -= 5
                c.setFont("Helvetica", 9)

            c.drawString(col_x, cursor_y, f"{point['const']}")
            c.drawString(col_x + col_spacing, cursor_y, f"{point['idx']}")
            c.drawString(col_x + col_spacing * 2, cursor_y, f"{point['x']:.3f}")
            c.drawString(col_x + col_spacing * 4.5, cursor_y, f"{point['y']:.3f}")

            cursor_y -= 14

    # ============================================================
    # OBSERVAÇÕES FINAIS (posicionado após as coordenadas)
    # ============================================================
    cursor_y -= 20

    if cursor_y < 120:
        c.showPage()
        cursor_y = height - 40

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, cursor_y, "Observações")
    cursor_y -= 16

    c.setFont("Helvetica", 10)
    c.drawString(
        46,
        cursor_y,
        "Este relatório foi gerado automaticamente a partir do arquivo DXF para fins acadêmicos.",
    )
    cursor_y -= 14

    c.drawString(
        46, cursor_y, "Não possui validade técnica ou responsabilidade profissional."
    )
    cursor_y -= 20

    c.drawString(
        46,
        cursor_y,
        "Proibido para uso profissional — somente para a disciplina de Topografia.",
    )

    c.showPage()
    c.save()

    return pdf_path
