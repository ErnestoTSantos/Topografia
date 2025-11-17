import os
import json
from datetime import datetime
import io

from django.conf import settings
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# matplotlib backend
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _make_thumbnail_from_geojson(geojson_obj, out_path, width_px=800, height_px=600):
    """Gera PNG com miniatura da planta."""
    if isinstance(geojson_obj, str):
        geojson_obj = json.loads(geojson_obj)

    polygons = []

    # Suporte a FeatureCollection
    if geojson_obj.get("type") == "FeatureCollection":
        for f in geojson_obj.get("features", []):
            g = f.get("geometry")
            if g and g.get("type") == "Polygon":
                polygons.append(g["coordinates"][0])

    elif geojson_obj.get("type") == "Polygon":
        polygons.append(geojson_obj["coordinates"][0])

    else:
        # fallback shapely __geo_interface__
        coords = geojson_obj.get("coordinates")
        if coords:
            polygons.append(coords[0])

    if not polygons:
        fig = plt.figure(figsize=(width_px / 100, height_px / 100), dpi=100)
        plt.text(0.5, 0.5, "Miniatura indisponível", ha="center", va="center")
        plt.axis("off")
        fig.savefig(out_path, bbox_inches="tight", pad_inches=0.2)
        plt.close(fig)
        return out_path

    fig, ax = plt.subplots(figsize=(width_px / 100, height_px / 100), dpi=100)

    for poly in polygons:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        ax.plot(xs, ys, linewidth=1.5, color="black")
        ax.fill(xs, ys, alpha=0.15)

    ax.set_aspect("equal", "box")
    ax.axis("off")

    all_x = [x for poly in polygons for x, _ in poly]
    all_y = [y for poly in polygons for _, y in poly]

    xmin, xmax = min(all_x), max(all_x)
    ymin, ymax = min(all_y), max(all_y)

    dx = (xmax - xmin) or 1
    dy = (ymax - ymin) or 1

    pad_x = dx * 0.08
    pad_y = dy * 0.08

    ax.set_xlim(xmin - pad_x, xmax + pad_x)
    ax.set_ylim(ymin - pad_y, ymax + pad_y)

    fig.savefig(out_path, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)

    return out_path


def generate_report_pdf(
    metadata: dict, plant_name: str, geojson_str: str = None
) -> str:
    """Gera PDF completo com miniatura, métricas e aviso acadêmico."""

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

    c.drawString(x_right, y, f"Área: {metadata.get('area_m2', 0):.3f} m²")
    y -= 16
    c.drawString(x_right, y, f"Perímetro: {metadata.get('perimeter_m', 0):.3f} m")
    y -= 16
    c.drawString(x_right, y, f"Vértices: {metadata.get('vertices', 0)}")
    y -= 16

    # ============================================================
    # LISTA DE LAYERS
    # ============================================================
    cursor_y = height - 105 - img_h - 40

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

    # ============================================================
    # OBSERVAÇÕES FINAIS
    # ============================================================
    cursor_y -= 20
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
