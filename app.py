import streamlit as st
import tempfile
import os
import re
import zipfile
import io
from pathlib import Path
from docling.document_converter import DocumentConverter

st.set_page_config(
    page_title="TokenSaver ⚡",
    page_icon="⚡",
    layout="wide",
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


tab1, tab2 = st.tabs(["📄 Conversão Individual", "📦 Conversão em Lote"])

with tab1:
    uploaded = st.file_uploader(
        "Arraste ou selecione um arquivo",
        type=["pdf", "docx", "xlsx"],
        help="Suporte a PDF, Word (.docx) e Excel (.xlsx)",
        key="single_file"
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

with tab2:
    st.write("Converta múltiplos arquivos de uma vez e baixe um ZIP com todos os Markdown gerados.")

    uploaded_files = st.file_uploader(
        "Arraste ou selecione múltiplos arquivos",
        type=["pdf", "docx", "xlsx"],
        help="Suporte a PDF, Word (.docx) e Excel (.xlsx)",
        accept_multiple_files=True,
        key="batch_files"
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
                    markdown_output = convert_file(tmp_path)
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
                        "status": f"❌ {str(exc)[:50]}"
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
        with st.expander("Ver lista de conversões"):
            for result in results:
                status_icon = result["status"]
                if result["status"] == "✅":
                    st.write(f"{status_icon} **{result['name']}.md** | {result['tokens']:,} tokens | {result['chars']:,} chars")
                else:
                    st.write(f"{status_icon} **{result['name']}**")

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
