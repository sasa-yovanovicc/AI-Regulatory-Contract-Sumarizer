import streamlit as st
import tempfile
import os
from summarizer.pipeline import summarize_document
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Regulatory Summarizer", layout="wide")

st.title("📄 Regulatory Summarizer")
st.caption("Sažimanje dugih regulatornih PDF dokumenata za bankarske službenike.")

with st.sidebar:
    st.header("⚙️ Podešavanja")
    focus = st.text_input("Fokus (opciono)", placeholder="npr. zaštita podataka klijenata")
    chunk_size = st.number_input("Veličina chunk-a (karakteri)", 1000, 8000, 3000, 250)
    overlap = st.number_input("Overlap", 0, 1000, 300, 50)
    model = st.text_input("OpenAI model", value=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    if model:
        os.environ["OPENAI_MODEL"] = model

uploaded = st.file_uploader("Upload PDF dokument", type=["pdf"])  # noqa: E501

if uploaded:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded.read())
        tmp_path = tmp.name

    run = st.button("Pokreni sažimanje")
    if run:
        with st.spinner("Obrađujem dokument..."):
            result = summarize_document(tmp_path, focus=focus, chunk_size=chunk_size, chunk_overlap=overlap)
        st.success("Gotovo!")
        st.subheader("Konačni sažetak")
        st.write(result["final_summary"])  # noqa: E501
        with st.expander("Detalji parcijalnih sažetaka"):
            st.write(f"Broj strana: {result['pages']}")
            st.write(f"Broj chunkova: {result['chunks']}")
            for i, ps in enumerate(result["partial_summaries"], 1):
                st.markdown(f"**Chunk {i}:** {ps}")
else:
    st.info("Upload-uj PDF da bi započeo.")

st.markdown("---")
st.caption("Demo alat – nije pravni savet. Koristi OpenAI API. ")
