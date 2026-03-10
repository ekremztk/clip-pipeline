"""
pdf_reporter.py — Clip Pipeline PDF Rapor Üreticisi
Her job için profesyonel bir PDF analiz raporu oluşturur.
"""

from pathlib import Path
import re
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import simpleSplit


# ── COLORS ────────────────────────────────────────────────────────────────────
C_BG        = colors.HexColor("#F2F2F7")
C_WHITE     = colors.white
C_BLACK     = colors.HexColor("#1C1C1E")
C_DARK      = colors.HexColor("#3A3A3C")
C_MID       = colors.HexColor("#8E8E93")
C_LIGHT     = colors.HexColor("#D1D1D6")
C_BLUE      = colors.HexColor("#007AFF")
C_GREEN     = colors.HexColor("#30D158")
C_YELLOW    = colors.HexColor("#FF9F0A")
C_RED       = colors.HexColor("#FF453A")
C_BLUE_SOFT = colors.HexColor("#EAF3FF")
C_CARD      = colors.white

def clean_for_pdf(text):
    if not text: return ""
    # Emojileri ve PDF'in Helvetica fontunu bozacak karakterleri siler
    # Sadece harfler, sayılar, Türkçe karakterler ve temel noktalama işaretleri kalır
    return re.sub(r'[^\w\s,.\-!?"\'ğüşöçıİĞÜŞÖÇ&:;%()\[\]/]', '', str(text))


def score_color(score):
    if score is None:
        return C_MID
    if score >= 85:
        return C_GREEN
    if score >= 70:
        return C_YELLOW
    return C_RED


def score_label(score):
    if score is None:
        return "—"
    if score >= 85:
        return "Yüksek"
    if score >= 70:
        return "Orta"
    return "Düşük"


def format_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02}:{m:02}:{s:02}"


# ── STYLES ────────────────────────────────────────────────────────────────────
def make_styles():
    return {
        "h_title": ParagraphStyle(
            "h_title",
            fontName="Helvetica-Bold",
            fontSize=26,
            textColor=C_WHITE,
            leading=32,
            alignment=TA_LEFT,
        ),
        "h_subtitle": ParagraphStyle(
            "h_subtitle",
            fontName="Helvetica",
            fontSize=12,
            textColor=colors.HexColor("#AEAEB2"),
            leading=16,
            alignment=TA_LEFT,
        ),
        "h_meta": ParagraphStyle(
            "h_meta",
            fontName="Helvetica",
            fontSize=9,
            textColor=colors.HexColor("#AEAEB2"),
            leading=13,
        ),
        "label": ParagraphStyle(
            "label",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=C_MID,
            leading=11,
            spaceBefore=4,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=10,
            textColor=C_DARK,
            leading=15,
            spaceAfter=4,
        ),
        "body_small": ParagraphStyle(
            "body_small",
            fontName="Helvetica",
            fontSize=9,
            textColor=C_DARK,
            leading=13,
        ),
        "clip_title": ParagraphStyle(
            "clip_title",
            fontName="Helvetica-Bold",
            fontSize=14,
            textColor=C_BLACK,
            leading=18,
        ),
        "clip_num": ParagraphStyle(
            "clip_num",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=C_BLUE,
            leading=11,
        ),
        "hashtag": ParagraphStyle(
            "hashtag",
            fontName="Helvetica",
            fontSize=9,
            textColor=C_BLUE,
            leading=13,
        ),
        "transcript": ParagraphStyle(
            "transcript",
            fontName="Courier",
            fontSize=9,
            textColor=C_DARK,
            leading=14,
            leftIndent=8,
        ),
        "recommendation": ParagraphStyle(
            "recommendation",
            fontName="Helvetica",
            fontSize=10,
            textColor=C_DARK,
            leading=15,
        ),
        "section_head": ParagraphStyle(
            "section_head",
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=C_MID,
            leading=12,
            spaceBefore=8,
            spaceAfter=3,
        ),
        "footer": ParagraphStyle(
            "footer",
            fontName="Helvetica",
            fontSize=8,
            textColor=C_MID,
            alignment=TA_CENTER,
        ),
    }


# ── CANVAS (header / footer on each page) ─────────────────────────────────────
class NumberedCanvas(rl_canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(num_pages)
            super().showPage()
        super().save()

    def _draw_footer(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(C_MID)
        self.drawCentredString(
            A4[0] / 2,
            12 * mm,
            f"Clip Pipeline Raporu  |  Sayfa {self._pageNumber} / {page_count}"
        )
        self.restoreState()


# ── SCORE BAR (drawn as Table) ────────────────────────────────────────────────
def score_bar_table(score, width=80*mm, height=6*mm):
    if score is None:
        score = 0
    filled = int(score / 100 * 20)
    sc = score_color(score)

    cells = []
    for i in range(20):
        c = sc if i < filled else C_LIGHT
        cells.append("")

    col_w = width / 20
    t = Table([cells], colWidths=[col_w] * 20, rowHeights=[height])
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, -1), C_LIGHT),
        ("GRID", (0, 0), (-1, -1), 0, C_WHITE),
        ("ROUNDEDCORNERS", [3]),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]
    for i in range(filled):
        style_cmds.append(("BACKGROUND", (i, 0), (i, 0), sc))
    t.setStyle(TableStyle(style_cmds))
    return t


# ── COVER PAGE ────────────────────────────────────────────────────────────────
def build_cover(story, styles, video_title, clip_count, now_str):
    # Dark header block via Table
    header_text = [
        [Paragraph("CLIP PIPELINE", styles["h_title"])],
        [Paragraph("Klip Analiz Raporu", styles["h_subtitle"])],
        [Spacer(1, 6*mm)],
        [Paragraph(f"<b>{video_title}</b>", ParagraphStyle(
            "vt", fontName="Helvetica-Bold", fontSize=13,
            textColor=C_WHITE, leading=18))],
        [Spacer(1, 3*mm)],
        [Paragraph(f"{clip_count} Klip  ·  {now_str}", styles["h_meta"])],
    ]
    cover_table = Table([[col] for col in header_text],
                        colWidths=[150*mm])
    cover_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_BLACK),
        ("LEFTPADDING", (0, 0), (-1, -1), 10*mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10*mm),
        ("TOPPADDING", (0, 0), (0, 0), 10*mm),
        ("BOTTOMPADDING", (-1, -1), (-1, -1), 10*mm),
        ("TOPPADDING", (0, 1), (-1, -1), 1*mm),
        ("BOTTOMPADDING", (0, 0), (-1, -2), 1*mm),
        ("ROUNDEDCORNERS", [8]),
    ]))
    story.append(cover_table)
    story.append(Spacer(1, 8*mm))


# ── SUMMARY TABLE ─────────────────────────────────────────────────────────────
def build_summary_table(story, styles, clips_data):
    story.append(Paragraph("ÖZET", styles["section_head"]))
    story.append(Spacer(1, 2*mm))

    header = ["#", "Başlık", "Süre", "Skor", "Potansiyel"]
    rows = [header]
    for i, clip in enumerate(clips_data):
        score = clip.get("score")
        rows.append([
            str(i + 1),
            clip["title"][:52] + ("..." if len(clip["title"]) > 52 else ""),
            f"{format_time(clip['start_sec'])} → {format_time(clip['end_sec'])}",
            str(score) if score else "—",
            score_label(score),
        ])

    col_widths = [8*mm, 72*mm, 28*mm, 12*mm, 22*mm]
    t = Table(rows, colWidths=col_widths)
    style_cmds = [
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), C_BLACK),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 3*mm),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 3*mm),
        # Body
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("TEXTCOLOR", (0, 1), (-1, -1), C_DARK),
        ("TOPPADDING", (0, 1), (-1, -1), 2.5*mm),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 2.5*mm),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_BG]),
        ("GRID", (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (3, 0), (3, -1), "CENTER"),
        ("ROUNDEDCORNERS", [4]),
    ]
    # Color score label column
    for i, clip in enumerate(clips_data):
        score = clip.get("score")
        c = score_color(score)
        style_cmds.append(("TEXTCOLOR", (4, i + 1), (4, i + 1), c))
        style_cmds.append(("FONTNAME", (4, i + 1), (4, i + 1), "Helvetica-Bold"))

    t.setStyle(TableStyle(style_cmds))
    story.append(t)
    story.append(Spacer(1, 6*mm))


# ── SINGLE CLIP CARD ──────────────────────────────────────────────────────────
def build_clip_section(story, styles, clip, index):
    score = clip.get("score")
    sc = score_color(score)
    duration = clip["end_sec"] - clip["start_sec"]

    elements = []

    # ── Clip header row
    clip_header = Table([[
        Paragraph(f"KLİP {index}", styles["clip_num"]),
        Paragraph(
            f"<font color='#{('%02x%02x%02x' % (int(sc.red*255), int(sc.green*255), int(sc.blue*255)))}'>"
            f"<b>{score}/100</b></font>  {score_label(score)} Viral Potansiyel",
            ParagraphStyle("sh", fontName="Helvetica", fontSize=9,
                           textColor=C_DARK, leading=12, alignment=TA_RIGHT)
        ),
    ]], colWidths=[80*mm, 70*mm])
    clip_header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(clip_header)
    elements.append(Spacer(1, 2*mm))
    elements.append(Paragraph(clean_for_pdf(clip["title"]), styles["clip_title"]))
    elements.append(Spacer(1, 2*mm))

    # Score bar
    elements.append(score_bar_table(score, width=150*mm, height=5*mm))
    elements.append(Spacer(1, 4*mm))

    # Timing + platform row
    info_data = [[
        Paragraph(f"<b>Zaman</b><br/>{format_time(clip['start_sec'])} → {format_time(clip['end_sec'])}  ({duration:.0f} sn)", styles["body_small"]),
        Paragraph(f"<b>Platform</b><br/>YouTube Shorts / TikTok / Reels", styles["body_small"]),
    ]]
    info_table = Table(info_data, colWidths=[75*mm, 75*mm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_BG),
        ("LEFTPADDING", (0, 0), (-1, -1), 4*mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4*mm),
        ("TOPPADDING", (0, 0), (-1, -1), 3*mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3*mm),
        ("ROUNDEDCORNERS", [4]),
        ("GRID", (0, 0), (-1, -1), 0, C_WHITE),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 4*mm))

    # Analysis fields
    fields = [
        ("NEDEN SEÇİLDİ", clip.get("why_selected")),
        ("HOOK  (İlk 2 Saniye)", clip.get("hook")),
        ("SES ANALİZİ", clip.get("audio_highlights")),
    ]
    trim = clip.get("trim_note", "none")
    if trim and trim.lower() != "none":
        fields.append(("EDİT NOTU", trim))

    for label, value in fields:
        if value:
            elements.append(Paragraph(label, styles["section_head"]))
            elements.append(Paragraph(clean_for_pdf(value), styles["body"]))
            elements.append(Spacer(1, 1*mm))

    # Publish block
    elements.append(Spacer(1, 3*mm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=C_LIGHT))
    elements.append(Spacer(1, 3*mm))
    elements.append(Paragraph("YAYINLANACAK İÇERİK", styles["section_head"]))
    elements.append(Spacer(1, 1*mm))

    publish_data = [
        [Paragraph("<b>Başlık</b>", styles["body_small"]),
         Paragraph(clean_for_pdf(clip["title"]), styles["body_small"])],
        [Paragraph("<b>Açıklama</b>", styles["body_small"]),
         Paragraph(clean_for_pdf(clip["description"]), styles["body_small"])],
        [Paragraph("<b>Hashtag</b>", styles["body_small"]),
         Paragraph(f'<font color="#007AFF">{clean_for_pdf(clip["hashtags"])}</font>', styles["body_small"])],
    ]
    pub_table = Table(publish_data, colWidths=[22*mm, 128*mm])
    pub_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_BLUE_SOFT),
        ("LEFTPADDING", (0, 0), (-1, -1), 4*mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4*mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5*mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5*mm),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D6E8FF")),
        ("ROUNDEDCORNERS", [4]),
    ]))
    elements.append(pub_table)

    # Transcript
    if clip.get("transcript"):
        elements.append(Spacer(1, 4*mm))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=C_LIGHT))
        elements.append(Spacer(1, 3*mm))
        elements.append(Paragraph("TRANSKRİPT", styles["section_head"]))
        elements.append(Spacer(1, 1*mm))
        trans_table = Table(
            [[Paragraph(clip["transcript"], styles["transcript"])]],
            colWidths=[150*mm]
        )
        trans_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_BG),
            ("LEFTPADDING", (0, 0), (-1, -1), 5*mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5*mm),
            ("TOPPADDING", (0, 0), (-1, -1), 3*mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3*mm),
            ("ROUNDEDCORNERS", [4]),
        ]))
        elements.append(trans_table)

    # Wrap in card
    card = Table([[e] for e in elements], colWidths=[150*mm])
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_WHITE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6*mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6*mm),
        ("TOPPADDING", (0, 0), (0, 0), 6*mm),
        ("BOTTOMPADDING", (-1, -1), (-1, -1), 6*mm),
        ("TOPPADDING", (0, 1), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -2), 0),
        ("ROUNDEDCORNERS", [8]),
        ("BOX", (0, 0), (-1, -1), 0.5, C_LIGHT),
    ]))
    story.append(KeepTogether(card))
    story.append(Spacer(1, 6*mm))


# ── MAIN ENTRY POINT ──────────────────────────────────────────────────────────
def write_pdf_report(clips_data: list[dict], job_id: str, video_title: str) -> str:
    job_dir = Path("output") / job_id
    pdf_path = str(job_dir / "report.pdf")
    now_str = datetime.now().strftime("%d %B %Y, %H:%M")

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=20*mm,
        rightMargin=20*mm,
        topMargin=20*mm,
        bottomMargin=20*mm,
        title=f"Clip Pipeline — {video_title}",
        author="Clip Pipeline",
    )

    styles = make_styles()
    story = []

    # Cover
    build_cover(story, styles, video_title, len(clips_data), now_str)

    # AI recommendation
    if clips_data and clips_data[0].get("recommendation"):
        story.append(Paragraph("AI TAVSİYESİ", styles["section_head"]))
        rec_table = Table(
            [[Paragraph(clips_data[0]["recommendation"], styles["recommendation"])]],
            colWidths=[150*mm]
        )
        rec_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_BLUE_SOFT),
            ("LEFTPADDING", (0, 0), (-1, -1), 5*mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5*mm),
            ("TOPPADDING", (0, 0), (-1, -1), 4*mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4*mm),
            ("ROUNDEDCORNERS", [6]),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D6E8FF")),
        ]))
        story.append(rec_table)
        story.append(Spacer(1, 6*mm))

    # Summary table
    build_summary_table(story, styles, clips_data)

    story.append(PageBreak())

    # Individual clip pages
    for i, clip in enumerate(clips_data):
        build_clip_section(story, styles, clip, i + 1)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[PDF Reporter] Saved: {pdf_path}")
    return pdf_path