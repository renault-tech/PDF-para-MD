import streamlit as st
import tempfile
import os
import re
from pathlib import Path
from docling.document_converter import DocumentConverter

st.set_page_config(
    page_title="TokenSaver ⚡",
    page_icon="⚡",
    layout="centered",
)

st.title("TokenSaver ⚡")
st.caption("Converta PDF, DOCX e XLSX em Markdown otimizado para LLMs — 100% local, zero custo de tokens.")


def clean_markdown(text: str) -> str:
    """Remove cabeçalhos e rodapés repetitivos comuns em PDFs."""
    lines = text.splitlines()
    line_freq: dict[str, int] = {}
    for line in lines:
        stripped = line.strip()
        if stripped:
            line_freq[stripped] = line_freq.get(stripped, 0) + 1

    total_pages_estimate = max(line_freq.values()) if line_freq else 1
    repetition_threshold = max(3, total_pages_estimate // 2)

    cleaned = [
        line for line in lines
        if line_freq.get(line.strip(), 0) < repetition_threshold or not line.strip()
    ]
    # Colapsar múltiplas linhas em branco consecutivas
    result = re.sub(r'\n{3,}', '\n\n', "\n".join(cleaned))
    return result.strip()


def convert_file(file_path: str) -> str:
    converter = DocumentConverter()
    result = converter.convert(file_path)
    raw_md = result.document.export_to_markdown()
    return clean_markdown(raw_md)


uploaded = st.file_uploader(
    "Arraste ou selecione um arquivo",
    type=["pdf", "docx", "xlsx"],
    help="Suporte a PDF, Word (.docx) e Excel (.xlsx)",
)

if uploaded:
    suffix = Path(uploaded.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded.read())
        tmp_path = tmp.name

    with st.spinner(f"Convertendo **{uploaded.name}** para Markdown…"):
        try:
            markdown_output = convert_file(tmp_path)
            st.session_state["md_output"] = markdown_output
            st.session_state["source_name"] = Path(uploaded.name).stem
        except Exception as exc:
            st.error(f"Erro na conversão: {exc}")
            markdown_output = None
        finally:
            os.unlink(tmp_path)

if "md_output" in st.session_state and st.session_state["md_output"]:
    md = st.session_state["md_output"]
    stem = st.session_state["source_name"]

    token_estimate = len(md.split())
    char_count = len(md)

    col1, col2 = st.columns(2)
    col1.metric("Palavras (aprox. tokens)", f"{token_estimate:,}")
    col2.metric("Caracteres", f"{char_count:,}")

    st.subheader("Visualização do Markdown")
    st.text_area("", value=md, height=400, label_visibility="collapsed")

    col_copy, col_dl = st.columns(2)

    with col_copy:
        st.components.v1.html(
            f"""
            <textarea id="md-content" style="display:none">{md.replace('"', '&quot;')}</textarea>
            <button onclick="navigator.clipboard.writeText(document.getElementById('md-content').value);
                            this.innerText='✅ Copiado!';"
                    style="width:100%;padding:8px 0;background:#4CAF50;color:white;
                           border:none;border-radius:6px;cursor:pointer;font-size:15px;">
                📋 Copiar para Clipboard
            </button>
            """,
            height=50,
        )

    with col_dl:
        st.download_button(
            label="⬇️ Baixar .md",
            data=md.encode("utf-8"),
            file_name=f"{stem}.md",
            mime="text/markdown",
            use_container_width=True,
        )
