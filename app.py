import streamlit as st
import tempfile
import os
import re
import zipfile
import io
from pathlib import Path
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

st.set_page_config(
    page_title="TokenSaver",
    page_icon="⚡",
    layout="wide",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif;
    }

    .main {
        background-color: #f5f5f7;
    }

    .block-container {
        max-width: 900px;
        padding-top: 1.5rem;
        padding-bottom: 1.5rem;
    }

    /* Reduce vertical gaps between stacked widgets */
    div[data-testid="stVerticalBlock"] > div {
        margin-bottom: 0 !important;
    }
    div[data-testid="stElementContainer"] {
        margin-bottom: 0.35rem;
    }

    /* Hero title */
    .ts-hero {
        text-align: center;
        margin-bottom: 1.2rem;
    }
    .ts-hero h1 {
        font-size: 2rem;
        font-weight: 700;
        letter-spacing: -0.03em;
        color: #1d1d1f;
        margin-bottom: 0.2rem;
    }
    .ts-hero p {
        font-size: 0.95rem;
        font-weight: 400;
        color: #6e6e73;
        margin: 0 auto;
        max-width: 520px;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background-color: #e8e8ed;
        padding: 4px;
        border-radius: 12px;
        justify-content: center;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 9px;
        padding: 8px 20px;
        font-weight: 500;
        color: #6e6e73;
        background-color: transparent;
    }
    .stTabs [aria-selected="true"] {
        background-color: #ffffff !important;
        color: #1d1d1f !important;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }

    /* Cards / containers */
    div[data-testid="stFileUploaderDropzone"] {
        background-color: #ffffff;
        border: 1.5px dashed #d2d2d7;
        border-radius: 16px;
    }
    div[data-testid="stFileUploaderDropzone"]:hover {
        border-color: #0071e3;
    }

    /* Metrics */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border-radius: 14px;
        padding: 1rem 1.2rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    div[data-testid="stMetricValue"] {
        color: #1d1d1f;
        font-weight: 700;
    }
    div[data-testid="stMetricLabel"] {
        color: #6e6e73;
    }

    /* Buttons */
    .stButton button, .stDownloadButton button {
        border-radius: 980px;
        font-weight: 600;
        border: none;
        padding: 0.6rem 1.4rem;
        background-color: #0071e3;
        color: white;
        transition: background-color 0.2s ease;
    }
    .stButton button:hover, .stDownloadButton button:hover {
        background-color: #0077ed;
        color: white;
    }

    /* Text area */
    textarea {
        border-radius: 14px !important;
        background-color: #ffffff !important;
        border: 1px solid #e5e5ea !important;
        font-family: 'SF Mono', 'Menlo', monospace !important;
        font-size: 0.85rem !important;
    }

    /* Subheaders */
    h3 {
        color: #1d1d1f;
        font-weight: 600;
        letter-spacing: -0.01em;
        margin-top: 0.6rem !important;
        margin-bottom: 0.4rem !important;
        font-size: 1.1rem !important;
    }

    /* Metrics: tighter padding for compact layout */
    div[data-testid="stMetric"] {
        padding: 0.6rem 0.9rem !important;
    }

    /* Progress bar */
    div[data-testid="stProgress"] > div > div {
        background-color: #0071e3;
    }

    /* Expander */
    details {
        background-color: #ffffff;
        border-radius: 14px;
        border: 1px solid #e5e5ea;
    }

    /* Hide default streamlit chrome */
    #MainMenu, footer, header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="ts-hero">
    <h1>TokenSaver ⚡</h1>
    <p>Converta PDF, DOCX e XLSX em Markdown otimizado para LLMs — 100% local, zero custo de tokens.</p>
</div>
""", unsafe_allow_html=True)


def _is_protected_line(stripped: str) -> bool:
    """Linhas de tabelas, títulos e listas nunca devem ser removidas pela limpeza."""
    return (
        stripped.startswith("|")
        or stripped.startswith("#")
        or stripped.startswith("-")
        or stripped.startswith("*")
        or stripped.startswith(">")
        or bool(re.match(r'^\d+[.)]\s', stripped))
    )


def clean_markdown(text: str) -> str:
    """Remove cabeçalhos/rodapés repetitivos comuns em PDFs, sem tocar em tabelas, títulos ou listas."""
    lines = text.splitlines()
    line_freq: dict[str, int] = {}
    for line in lines:
        stripped = line.strip()
        if stripped and not _is_protected_line(stripped):
            line_freq[stripped] = line_freq.get(stripped, 0) + 1

    total_pages_estimate = max(line_freq.values()) if line_freq else 1
    # Threshold conservador: só remove linhas curtas repetidas MUITAS vezes
    # (típico de cabeçalho/rodapé de página), nunca conteúdo estrutural.
    repetition_threshold = max(5, total_pages_estimate)

    cleaned = [
        line for line in lines
        if not line.strip()
        or _is_protected_line(line.strip())
        or len(line.strip()) > 80
        or line_freq.get(line.strip(), 0) < repetition_threshold
    ]
    # Colapsar múltiplas linhas em branco consecutivas
    result = re.sub(r'\n{3,}', '\n\n', "\n".join(cleaned))
    return result.strip()


def _build_converter() -> DocumentConverter:
    # EasyOCR no lugar do motor padrão (PP-OCRv6/torch), que trava com
    # "Unsupported configuration" neste ambiente. EasyOCR é maduro e
    # estável, cobrindo tanto PDFs digitais quanto escaneados/imagens.
    pdf_options = PdfPipelineOptions(
        do_ocr=True,
        ocr_options=EasyOcrOptions(lang=["pt", "en"]),
    )
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options)}
    )


def convert_file(file_path: str, remove_repeated: bool = False) -> str:
    converter = _build_converter()
    result = converter.convert(file_path)
    raw_md = result.document.export_to_markdown()
    if remove_repeated:
        return clean_markdown(raw_md)
    return raw_md.strip()


tab1, tab2 = st.tabs(["📄 Conversão Individual", "📦 Conversão em Lote"])

with tab1:
    uploaded = st.file_uploader(
        "Arraste ou selecione um arquivo",
        type=["pdf", "docx", "xlsx"],
        help="Suporte a PDF, Word (.docx) e Excel (.xlsx)",
        key="single_file"
    )
    remove_repeated_single = st.checkbox(
        "Remover cabeçalhos/rodapés repetitivos",
        value=False,
        help="Desligado por padrão para garantir conversão íntegra, sem perda de texto ou tabelas.",
        key="remove_repeated_single"
    )

    if uploaded:
        suffix = Path(uploaded.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name

        with st.spinner(f"Convertendo **{uploaded.name}** para Markdown…"):
            try:
                markdown_output = convert_file(tmp_path, remove_repeated=remove_repeated_single)
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
        st.text_area("", value=md, height=280, label_visibility="collapsed")

        col_copy, col_dl = st.columns(2)

        with col_copy:
            st.components.v1.html(
                f"""
                <textarea id="md-content" style="display:none">{md.replace('"', '&quot;')}</textarea>
                <button onclick="navigator.clipboard.writeText(document.getElementById('md-content').value);
                                this.innerText='✅ Copiado!';"
                        style="width:100%;padding:10px 0;background:#0071e3;color:white;
                               border:none;border-radius:980px;cursor:pointer;font-size:14px;
                               font-weight:600;font-family:'Inter',-apple-system,sans-serif;
                               transition:background-color 0.2s ease;"
                        onmouseover="this.style.backgroundColor='#0077ed'"
                        onmouseout="this.style.backgroundColor='#0071e3'">
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

with tab2:
    st.write("Converta múltiplos arquivos de uma vez e baixe um ZIP com todos os Markdown gerados.")

    uploaded_files = st.file_uploader(
        "Arraste ou selecione múltiplos arquivos",
        type=["pdf", "docx", "xlsx"],
        help="Suporte a PDF, Word (.docx) e Excel (.xlsx)",
        accept_multiple_files=True,
        key="batch_files"
    )
    remove_repeated_batch = st.checkbox(
        "Remover cabeçalhos/rodapés repetitivos",
        value=False,
        help="Desligado por padrão para garantir conversão íntegra, sem perda de texto ou tabelas.",
        key="remove_repeated_batch"
    )

    if uploaded_files:
        st.write(f"**{len(uploaded_files)} arquivo(s) selecionado(s)**")

        if st.button("🚀 Converter Todos", use_container_width=True):
            progress_bar = st.progress(0)
            status_text = st.empty()
            results = []

            total_tokens = 0
            total_chars = 0
            successful = 0
            failed = 0

            for idx, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"Processando {idx + 1}/{len(uploaded_files)}: {uploaded_file.name}…")
                progress = (idx) / len(uploaded_files)
                progress_bar.progress(progress)

                suffix = Path(uploaded_file.name).suffix
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(uploaded_file.read())
                    tmp_path = tmp.name

                try:
                    markdown_output = convert_file(tmp_path, remove_repeated=remove_repeated_batch)
                    file_stem = Path(uploaded_file.name).stem

                    results.append({
                        "name": file_stem,
                        "content": markdown_output,
                        "tokens": len(markdown_output.split()),
                        "chars": len(markdown_output),
                        "status": "✅"
                    })

                    total_tokens += len(markdown_output.split())
                    total_chars += len(markdown_output)
                    successful += 1

                except Exception as exc:
                    results.append({
                        "name": Path(uploaded_file.name).stem,
                        "content": None,
                        "status": "❌",
                        "error": str(exc)
                    })
                    failed += 1
                finally:
                    os.unlink(tmp_path)

            progress_bar.progress(1.0)
            status_text.text(f"✅ Conversão concluída! {successful} sucesso, {failed} erro(s).")

            st.session_state["batch_results"] = results
            st.session_state["batch_total_tokens"] = total_tokens
            st.session_state["batch_total_chars"] = total_chars

    if "batch_results" in st.session_state and st.session_state["batch_results"]:
        results = st.session_state["batch_results"]

        st.subheader("📊 Estatísticas")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Arquivos Convertidos", len([r for r in results if r["status"] == "✅"]))
        col2.metric("Erros", len([r for r in results if r["status"] != "✅"]))
        col3.metric("Total de Palavras", f"{st.session_state['batch_total_tokens']:,}")
        col4.metric("Total de Caracteres", f"{st.session_state['batch_total_chars']:,}")

        st.subheader("📋 Arquivos")
        has_errors = any(r["status"] != "✅" for r in results)
        with st.expander("Ver lista de conversões", expanded=has_errors):
            list_container = st.container(height=260)
            with list_container:
                for result in results:
                    if result["status"] == "✅":
                        st.write(f"✅ **{result['name']}.md** | {result['tokens']:,} tokens | {result['chars']:,} chars")
                    else:
                        st.write(f"❌ **{result['name']}**")
                        st.code(result.get("error", "Erro desconhecido"), language=None)

        if any(r["status"] == "✅" for r in results):
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for result in results:
                    if result["status"] == "✅":
                        zip_file.writestr(f"{result['name']}.md", result["content"].encode("utf-8"))

            zip_buffer.seek(0)
            st.download_button(
                label="⬇️ Baixar ZIP com todos os arquivos",
                data=zip_buffer.getvalue(),
                file_name="conversao-em-lote.zip",
                mime="application/zip",
                use_container_width=True,
            )
