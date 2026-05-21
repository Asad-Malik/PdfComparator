"""
PDF Comparison Dashboard (Character-by-Character)
==================================================
Upload two PDF files, compare them character-by-character, and view all three side-by-side:
  • PDF 1  – Original (baseline)
  • PDF 2  – Revised
  • PDF 3  – Revised with changes highlighted (yellow = new, orange = modified)

This dashboard uses CHARACTER-BY-CHARACTER comparison (exact, case-sensitive).
Even a single digit or punctuation change triggers a highlight on the entire line.

Run:
    streamlit run dashboard_charcomp.py
"""

import base64
import difflib
import io
from pathlib import Path

import fitz  # PyMuPDF
import streamlit as st

# ── Thresholds (can be changed via the sidebar) ────────────────────────────────
DEFAULT_UNCHANGED  = 1.0    # 100% exact match only = no change
DEFAULT_MODIFIED   = 0.50   # between this and UNCHANGED → modified
DEFAULT_MIN_CHARS  = 1

COLOR_NEW      = (1.0, 1.0, 0.0)   # yellow
COLOR_MODIFIED = (1.0, 0.65, 0.0)  # orange
# ──────────────────────────────────────────────────────────────────────────────


# ── Core comparison helpers (CHARACTER-BY-CHARACTER) ──────────────────────────

def extract_lines(pdf_bytes: bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    lines = []
    for page_idx, page in enumerate(doc):
        for raw in page.get_text("text").splitlines():
            text = raw.strip()
            if text:
                lines.append({"text": text, "page": page_idx})
    doc.close()
    return lines


def char_count(text: str) -> int:
    return len(text)


def compare_character_sequences(lines1, lines2, unchanged_thresh, modified_thresh, min_chars):
    """
    CHARACTER-BY-CHARACTER comparison (exact, case-sensitive).
    """
    pool1 = [
        item["text"]
        for item in lines1
        if char_count(item["text"]) >= min_chars
    ]

    changes = []
    for item2 in lines2:
        text2 = item2["text"]
        if char_count(text2) < min_chars:
            continue

        best_score, best_match = 0.0, ""

        for text1 in pool1:
            score = difflib.SequenceMatcher(None, text2, text1).ratio()
            if score > best_score:
                best_score = score
                best_match = text1

        if best_score >= unchanged_thresh:
            continue

        status = "modified" if best_score >= modified_thresh else "new"
        changes.append({
            "text":       text2,
            "page":       item2["page"],
            "status":     status,
            "score":      best_score,
            "best_match": best_match,
        })

    return changes


def build_highlighted_pdf(pdf2_bytes: bytes, changes) -> bytes:
    doc = fitz.open(stream=pdf2_bytes, filetype="pdf")

    for change in changes:
        page = doc[change["page"]]
        color = COLOR_NEW if change["status"] == "new" else COLOR_MODIFIED
        
        # Strategy 1: Try entire line
        rects = page.search_for(change["text"])
        
        if rects:
            for rect in rects:
                annot = page.add_highlight_annot(rect)
                annot.set_colors(stroke=color)
                annot.update()
        else:
            # Strategy 2: Try first 50 chars
            if len(change["text"]) > 20:
                partial = change["text"][:50]
                rects = page.search_for(partial)
                if rects:
                    for rect in rects:
                        annot = page.add_highlight_annot(rect)
                        annot.set_colors(stroke=color)
                        annot.update()
            
            # Strategy 3: Try last 50 chars
            if not rects and len(change["text"]) > 20:
                partial = change["text"][-50:]
                rects = page.search_for(partial)
                if rects:
                    for rect in rects:
                        annot = page.add_highlight_annot(rect)
                        annot.set_colors(stroke=color)
                        annot.update()
            
            # Strategy 4: Search for changed characters only
            if not rects and change["status"] == "modified" and change["best_match"]:
                differ = difflib.Differ()
                diff = list(differ.compare(change["best_match"], change["text"]))
                added = ''.join([c[2] for c in diff if c.startswith('+ ')])
                
                if added and len(added) < 20:
                    rects = page.search_for(added)
                    for rect in rects:
                        annot = page.add_highlight_annot(rect)
                        annot.set_colors(stroke=color)
                        annot.update()

    buf = io.BytesIO()
    doc.save(buf, garbage=4, deflate=True)
    doc.close()
    return buf.getvalue()


# ── PDF viewer helper ──────────────────────────────────────────────────────────

def pdf_iframe(pdf_bytes: bytes, label: str, height: int = 900):
    b64 = base64.b64encode(pdf_bytes).decode()
    st.markdown(f"**{label}**")
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{b64}" '
        f'width="100%" height="{height}px" '
        'style="border:1px solid #ccc; border-radius:6px;"></iframe>',
        unsafe_allow_html=True,
    )


# ── Page layout ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="PDF Comparison Dashboard (Character-by-Character)",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📄 PDF Comparison Dashboard (Character-by-Character)")
st.caption("Character-exact comparison: detects even single digit/punctuation changes. Full line highlighting.")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")
    
    st.markdown("**Comparison Type: CHARACTER-BY-CHARACTER**")
    st.markdown("Exact match required (case-sensitive). No normalization.")

    unchanged_thresh = st.slider(
        "Unchanged threshold",
        min_value=0.95, max_value=1.00, value=DEFAULT_UNCHANGED, step=0.01,
        help="Lines scoring ≥ this are considered unchanged. "
             "Default (1.0) catches every single character difference.",
    )
    modified_thresh = st.slider(
        "Modified threshold",
        min_value=0.30, max_value=float(unchanged_thresh) - 0.01,
        value=min(DEFAULT_MODIFIED, float(unchanged_thresh) - 0.01),
        step=0.01,
        help="Lines between this and unchanged threshold are highlighted orange (modified). Below → yellow (new).",
    )
    min_chars = st.number_input(
        "Minimum characters per line",
        min_value=1, max_value=20, value=DEFAULT_MIN_CHARS, step=1,
        help="Lines with fewer characters than this are ignored.",
    )
    viewer_height = st.slider("Viewer height (px)", 400, 1400, 900, step=50)

    st.markdown("---")
    st.markdown("**Examples detected:**")
    st.markdown("• Single digit: `123` → `121` ✓")
    st.markdown("• Comma: `text,` → `text` ✓")
    st.markdown("• Space: `hello world` → `helloworld` ✓")
    st.markdown("• Case: `Hello` → `hello` ✓")
    st.markdown("")
    st.markdown("🟡 **Yellow** = New content")
    st.markdown("🟠 **Orange** = Modified content")

# ── File uploaders ────────────────────────────────────────────────────────────
col_up1, col_up2 = st.columns(2)

with col_up1:
    upload1 = st.file_uploader("📂 Upload PDF 1 – Original (Baseline)", type="pdf", key="pdf1_char")

with col_up2:
    upload2 = st.file_uploader("📂 Upload PDF 2 – Revised", type="pdf", key="pdf2_char")

# ── Run comparison ────────────────────────────────────────────────────────────
if upload1 and upload2:
    pdf1_bytes = upload1.read()
    pdf2_bytes = upload2.read()

    with st.spinner("Comparing PDFs character-by-character … this may take a moment for large documents."):
        lines1   = extract_lines(pdf1_bytes)
        lines2   = extract_lines(pdf2_bytes)
        changes  = compare_character_sequences(
            lines1, lines2,
            unchanged_thresh, modified_thresh, int(min_chars)
        )
        highlighted_bytes = build_highlighted_pdf(pdf2_bytes, changes)

    # ── Summary stats ─────────────────────────────────────────────────────────
    new_count = sum(1 for c in changes if c["status"] == "new")
    mod_count = sum(1 for c in changes if c["status"] == "modified")

    st.success(f"Comparison complete — **{new_count}** new lines (🟡) · **{mod_count}** modified lines (🟠)")

    m1, m2, m3 = st.columns(3)
    m1.metric("Lines in Original", len(lines1))
    m2.metric("Lines in Revised",  len(lines2))
    m3.metric("Changed lines",     len(changes))

    st.markdown("---")

    # ── Three-column PDF viewer ───────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)

    with c1:
        pdf_iframe(pdf1_bytes, f"📄 PDF 1 – {upload1.name}", viewer_height)

    with c2:
        pdf_iframe(pdf2_bytes, f"📄 PDF 2 – {upload2.name}", viewer_height)

    with c3:
        pdf_iframe(highlighted_bytes, "🔍 PDF 2 – Highlighted Changes (Char-by-Char)", viewer_height)

    # ── Download button ───────────────────────────────────────────────────────
    st.markdown("---")
    st.download_button(
        label="⬇️ Download Highlighted PDF",
        data=highlighted_bytes,
        file_name="highlighted_changes_charcomp.pdf",
        mime="application/pdf",
    )

    # ── Change detail table ───────────────────────────────────────────────────
    with st.expander("📋 View all changes in detail"):
        if changes:
            import pandas as pd
            
            detail_rows = []
            for c in changes:
                # Extract character-level changes
                char_changes = "—"
                if c["status"] == "modified" and c["best_match"]:
                    differ = difflib.Differ()
                    diff = list(differ.compare(c["best_match"], c["text"]))
                    removed = ''.join([d[2] for d in diff if d.startswith('- ')])
                    added = ''.join([d[2] for d in diff if d.startswith('+ ')])
                    if removed or added:
                        char_changes = f"Removed: {repr(removed)[:30]}, Added: {repr(added)[:30]}"
                
                detail_rows.append({
                    "Page":   c["page"] + 1,
                    "Status": c["status"].upper(),
                    "Score":  round(c["score"], 2),
                    "PDF 2":  c["text"][:60] + ("..." if len(c["text"]) > 60 else ""),
                    "Character Changes": char_changes,
                })
            
            df = pd.DataFrame(detail_rows)
            st.dataframe(df, use_container_width=True, height=400)
        else:
            st.info("No changes detected with the current thresholds.")

else:
    st.info("👆 Please upload both PDF files using the uploaders above to start the comparison.")
