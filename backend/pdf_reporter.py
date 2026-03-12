"""
pdf_reporter.py — Clip Pipeline PDF Rapor Üreticisi
Her job için profesyonel bir PDF analiz raporu oluşturur.
"""

import re
from pathlib import Path
from datetime import datetime

from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.lib import colors  # type: ignore[import-untyped]
from reportlab.lib.units import mm  # type: ignore[import-untyped]
from reportlab.lib.styles import ParagraphStyle  # type: ignore[import-untyped]
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT  # type: ignore[import-untyped]
from reportlab.platypus import (  # type: ignore[import-untyped]
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.pdfgen import canvas as rl_canvas  # type: ignore[import-untyped]
from reportlab.lib.utils import simpleSplit  # type: ignore[import-untyped]


# ── PDF İÇİN EMOJİ/ÖZEL KARAKTER TEMİZLEYİCİ ──────────────────────────────────
def clean_for_pdf(text):
    if not text: return ""
    # Emojileri ve PDF fontunu bozabilecek karakterleri engeller
    return re.sub(r'[^\w\s,.\-!?"\'ğüşöçıİĞÜŞÖÇ&:;%()\[\]/]', '', str(text))


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


def score_color(score):
    if score is None:
        return C_MID
    try:
        score = int(score)
    except:
        score = 0
    if score >= 85:
        return C_GREEN
    if score >= 70:
        return C_YELLOW
    return C_RED


def score_label(score):
    if score is None:
        return "—"
    try:
        score = int(score)
    except:
        score = 0
    if score >= 85:
        return "High"
    if score >= 70:
        return "Medium"
    return "Low"


def format_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02}:{m:02}:{s:02}"


# ── STYLES ────────────────────────────────────────────────────────────────────
def make_styles():
    return {
        "h_title": ParagraphStyle(
            "h_title", fontName="Helvetica-Bold", fontSize=26,
            textColor=C_WHITE, leading=32, alignment=TA_LEFT,
        ),
        "h_subtitle": ParagraphStyle(
            "h_subtitle", fontName="Helvetica", fontSize=12,
            textColor=colors.HexColor("#AEAEB2"), leading=16, alignment=TA_LEFT,
        ),
        "h_meta": ParagraphStyle(
            "h_meta", fontName="Helvetica", fontSize=9,
            textColor=colors.HexColor("#AEAEB2"), leading=13,
        ),
        "label": ParagraphStyle(
            "label", fontName="Helvetica-Bold", fontSize=8,
            textColor=C_MID, leading=11, spaceBefore=4,
        ),
        "body": ParagraphStyle(
            "body", fontName="Helvetica", fontSize=10,
            textColor=C_DARK, leading=15, spaceAfter=4,
        ),
        "body_small": ParagraphStyle(
            "body_small", fontName="Helvetica", fontSize=9,
            textColor=C_DARK, leading=13,
        ),
        "clip_title": ParagraphStyle(
            "clip_title", fontName="Helvetica-Bold", fontSize=14,
            textColor=C_BLACK, leading=18,
        ),
        "clip_num": ParagraphStyle(
            "clip_num", fontName="Helvetica-Bold", fontSize=8,
            textColor=C_BLUE, leading=11,
        ),
        "transcript": ParagraphStyle(
            "transcript", fontName="Courier", fontSize=9,
            textColor=C_DARK, leading=14, leftIndent=8,
        ),
        "recommendation": ParagraphStyle(
            "recommendation", fontName="Helvetica", fontSize=10,
            textColor=C_DARK, leading=15,
        ),
        "section_head": ParagraphStyle(
            "section_head", fontName="Helvetica-Bold", fontSize=9,
            textColor=C_MID, leading=12, spaceBefore=8, spaceAfter=3,
        ),
    }


# ── CANVAS (header / footer) ──────────────────────────────────────────────────
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
            f"Clip Analysis Report  |  Page {self._pageNumber} / {page_count}"
        )
        self.restoreState()


# ── SCORE BAR ─────────────────────────────────────────────────────────────────
def score_bar_table(score, width=80*mm, height=6*mm):
    if score is None: score = 0
    try: score = int(score)
    except: score = 0
    
    filled = int(score / 100 * 20)
    sc = score_color(score)

    cells = [""] * 20
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
    header_text = [
        [Paragraph("CLIP PIPELINE", styles["h_title"])],
        [Paragraph("AI Clip Analysis Report", styles["h_subtitle"])],
        [Spacer(1, 6*mm)],
        [Paragraph(f"<b>{clean_for_pdf(video_title)}</b>", ParagraphStyle(
            "vt", fontName="Helvetica-Bold", fontSize=13,
            textColor=C_WHITE, leading=18))],
        [Spacer(1, 3*mm)],
        [Paragraph(f"{clip_count} Clips  ·  {now_str}", styles["h_meta"])],
    ]
    cover_table = Table([[col] for col in header_text], colWidths=[150*mm])
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
    story.append(Paragraph("SUMMARY", styles["section_head"]))
    story.append(Spacer(1, 2*mm))

    header = ["#", "Title", "Duration", "Score", "Potential"]
    rows = [header]
    for i, clip in enumerate(clips_data):
        score = clip.get("score")
        title_clean = clean_for_pdf(clip.get("title", ""))
        rows.append([
            str(i + 1),
            title_clean[:52] + ("..." if len(title_clean) > 52 else ""),  # type: ignore[index]
            f"{format_time(clip['start_sec'])} → {format_time(clip['end_sec'])}",
            str(score) if score else "—",
            score_label(score),
        ])

    t = Table(rows, colWidths=[8*mm, 72*mm, 28*mm, 12*mm, 22*mm])
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), C_BLACK),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 3*mm),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 3*mm),
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
    for i, clip in enumerate(clips_data):
        c = score_color(clip.get("score"))
        style_cmds.append(("TEXTCOLOR", (4, i + 1), (4, i + 1), c))
        style_cmds.append(("FONTNAME", (4, i + 1), (4, i + 1), "Helvetica-Bold"))

    t.setStyle(TableStyle(style_cmds))
    story.append(t)
    story.append(Spacer(1, 6*mm))


# ── SINGLE CLIP CARD ──────────────────────────────────────────────────────────
def build_clip_section(story, styles, clip, index):
    score = clip.get("score", 0)
    sc = score_color(score)
    duration = clip["end_sec"] - clip["start_sec"]
    elements = []

    clip_header = Table([[
        Paragraph(f"CLIP {index}", styles["clip_num"]),
        Paragraph(
            f"<font color='#{('%02x%02x%02x' % (int(sc.red*255), int(sc.green*255), int(sc.blue*255)))}'>"
            f"<b>{score}/100</b></font>  {score_label(score)} Viral Potential",
            ParagraphStyle("sh", fontName="Helvetica", fontSize=9, textColor=C_DARK, alignment=TA_RIGHT)
        ),
    ]], colWidths=[80*mm, 70*mm])
    clip_header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("PADDING", (0, 0), (-1, -1), 0)]))
    
    elements.extend([
        clip_header, Spacer(1, 2*mm),
        Paragraph(clean_for_pdf(clip.get("title", "")), styles["clip_title"]), Spacer(1, 2*mm),
        score_bar_table(score, width=150*mm, height=5*mm), Spacer(1, 4*mm)
    ])

    info_data = [[
        Paragraph(f"<b>Time</b><br/>{format_time(clip['start_sec'])} → {format_time(clip['end_sec'])}  ({duration:.0f} sec)", styles["body_small"]),
        Paragraph(f"<b>Platform</b><br/>YouTube Shorts / TikTok / Reels", styles["body_small"]),
    ]]
    info_table = Table(info_data, colWidths=[75*mm, 75*mm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_BG),
        ("PADDING", (0, 0), (-1, -1), 4*mm),
        ("ROUNDEDCORNERS", [4]), ("GRID", (0, 0), (-1, -1), 0, C_WHITE),
    ]))
    elements.extend([info_table, Spacer(1, 4*mm)])

    fields = [
        ("WHY SELECTED", clip.get("why_selected")),
        ("HOOK (First 3 Sec)", clip.get("hook")),
        ("EDIT NOTE", clip.get("trim_note"))
    ]
    for label, value in fields:
        if value and str(value).lower() != "none":
            elements.extend([
                Paragraph(label, styles["section_head"]),
                Paragraph(clean_for_pdf(value), styles["body"]),
                Spacer(1, 1*mm)
            ])

    elements.extend([
        Spacer(1, 3*mm), HRFlowable(width="100%", thickness=0.5, color=C_LIGHT), Spacer(1, 3*mm),
        Paragraph("PUBLISHING CONTENT", styles["section_head"]), Spacer(1, 1*mm)
    ])

    pub_table = Table([
        [Paragraph("<b>Title</b>", styles["body_small"]), Paragraph(clean_for_pdf(clip.get("title", "")), styles["body_small"])],
        [Paragraph("<b>Desc</b>", styles["body_small"]), Paragraph(clean_for_pdf(clip.get("description", "")), styles["body_small"])],
        [Paragraph("<b>Tags</b>", styles["body_small"]), Paragraph(f'<font color="#007AFF">{clean_for_pdf(clip.get("hashtags", ""))}</font>', styles["body_small"])],
    ], colWidths=[15*mm, 135*mm])
    pub_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_BLUE_SOFT),
        ("PADDING", (0, 0), (-1, -1), 4*mm),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D6E8FF")),
        ("ROUNDEDCORNERS", [4]),
    ]))
    elements.append(pub_table)

    if clip.get("transcript"):
        elements.extend([
            Spacer(1, 4*mm), HRFlowable(width="100%", thickness=0.5, color=C_LIGHT), Spacer(1, 3*mm),
            Paragraph("TRANSCRIPT", styles["section_head"]), Spacer(1, 1*mm)
        ])
        trans_table = Table([[Paragraph(clean_for_pdf(clip["transcript"]), styles["transcript"])]], colWidths=[150*mm])
        trans_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_BG), ("PADDING", (0, 0), (-1, -1), 5*mm), ("ROUNDEDCORNERS", [4]),
        ]))
        elements.append(trans_table)

    card = Table([[e] for e in elements], colWidths=[150*mm])
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_WHITE),
        ("PADDING", (0, 0), (-1, -1), 6*mm),
        ("ROUNDEDCORNERS", [8]), ("BOX", (0, 0), (-1, -1), 0.5, C_LIGHT),
    ]))
    story.extend([KeepTogether(card), Spacer(1, 6*mm)])


# ── MAIN ENTRY POINT ──────────────────────────────────────────────────────────
def write_pdf_report(clips_data: list[dict], job_id: str, video_title: str) -> str:
    job_dir = Path("output") / job_id
    pdf_path = str(job_dir / "report.pdf")
    now_str = datetime.now().strftime("%d %b %Y, %H:%M")

    doc = SimpleDocTemplate(
        pdf_path, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm,
        title=f"Clip Analysis — {clean_for_pdf(video_title)}", author="Clip Pipeline",
    )
    styles = make_styles()
    story = []

    build_cover(story, styles, video_title, len(clips_data), now_str)
    build_summary_table(story, styles, clips_data)
    story.append(PageBreak())

    for i, clip in enumerate(clips_data):
        build_clip_section(story, styles, clip, i + 1)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[PDF Reporter] Saved: {pdf_path}")
    return pdf_path