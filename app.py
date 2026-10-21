"""Streamlit UI for the local RAG assistant.

Run with: ``streamlit run app.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.rag.chunker import MAX_CHARS, OVERLAP_CHARS, chunk_documents  # noqa: E402
from src.rag.config import Settings  # noqa: E402
from src.rag.index import Index  # noqa: E402
from src.rag.loader import load_documents  # noqa: E402
from src.rag.pipeline import AskResult, RagPipeline  # noqa: E402

st.set_page_config(page_title="Local Docs RAG", page_icon="📚", layout="wide")


@st.cache_resource(show_spinner=False)
def get_pipeline() -> RagPipeline:
    return RagPipeline()


def page_label(page: int | None) -> str:
    return f"page {page}" if page is not None else "text"


def render_answer(result: AskResult) -> None:
    if result.abstained:
        st.warning(result.answer)
    else:
        st.markdown(result.answer)

    if result.citations:
        st.markdown("**Sources cited**")
        for citation in result.citations:
            st.markdown(
                f"- `{citation['marker']}` **{citation['source']}**, "
                f"{page_label(citation['page'])} "
                f"(similarity {citation['score']:.3f})"
            )

    if result.retrieved:
        with st.expander(f"Retrieved passages ({len(result.retrieved)})", expanded=False):
            for number, chunk in enumerate(result.retrieved, start=1):
                st.markdown(
                    f"**[{number}] {chunk.source}**, {page_label(chunk.page)} "
                    f"· score `{chunk.score:.3f}`"
                )
                st.caption(chunk.text[:700] + ("…" if len(chunk.text) > 700 else ""))
                if number < len(result.retrieved):
                    st.divider()

    st.caption(f"{result.latency_ms:.0f} ms · generated locally with Ollama")


def main() -> None:
    try:
        settings = Settings.from_env()
    except ValueError as error:
        st.error(f"Configuration error: {error}")
        st.stop()

    st.title("📚 Local Docs RAG")
    st.caption(
        "Ask questions about the documents in `data/documents/`. "
        "Embeddings, retrieval and generation run locally."
    )

    try:
        pipeline = get_pipeline()
    except Exception as error:  # noqa: BLE001 - shown to the user
        st.error(f"Could not initialize the assistant: {error}")
        st.stop()

    documents = load_documents(settings.docs_dir)
    chunks = chunk_documents(documents, max_chars=MAX_CHARS, overlap_chars=OVERLAP_CHARS)
    fingerprint = Index.fingerprint(
        chunks,
        embed_model=settings.embed_model,
        max_chars=MAX_CHARS,
        overlap_chars=OVERLAP_CHARS,
    )
    index_current = pipeline.index.is_current(fingerprint)
    stats = pipeline.status()

    # ------------------------------------------------------------------ sidebar
    with st.sidebar:
        st.header("Index")
        if index_current:
            st.success("Index is up to date")
        else:
            st.warning("Index is empty or out of date")

        st.metric("Chunks indexed", stats["chunks"])
        st.caption(f"Embedding model: `{settings.embed_model}`")
        st.caption(f"Chat model: `{settings.chat_model}`")
        if stats.get("updated_at"):
            st.caption(f"Last indexed: {stats['updated_at']}")

        build_col, rebuild_col = st.columns(2)
        build = build_col.button("Build", use_container_width=True, type="primary")
        rebuild = rebuild_col.button("Rebuild", use_container_width=True)

        if build or rebuild:
            progress_bar = st.progress(0.0, text="Indexing documents…")

            def update(done: int, total: int) -> None:
                progress_bar.progress(done / total, text=f"Embedding chunks {done}/{total}")

            try:
                report = pipeline.build_index(force=rebuild, progress=update)
                progress_bar.empty()
                if report.rebuilt:
                    st.success(f"Indexed {report.chunks} chunks from {report.documents} documents.")
                else:
                    st.info("The index was already current; nothing to rebuild.")
                stats = pipeline.status()
                index_current = True
            except Exception as error:  # noqa: BLE001
                progress_bar.empty()
                st.error(str(error))

        st.divider()
        st.subheader("Retrieval")
        top_k = st.slider("Passages to retrieve", 1, 5, settings.top_k)
        threshold = st.slider(
            "Similarity threshold",
            0.0,
            1.0,
            settings.similarity_threshold,
            0.05,
            help="Chunks below this cosine similarity are discarded. Tune it on the validation split.",
        )

        st.divider()
        source_pages: dict[str, list[str]] = {}
        for document in documents:
            source_pages.setdefault(document.source, []).append(
                f"p. {document.page}" if document.page is not None else "text"
            )
        with st.expander(f"Documents ({len(source_pages)})"):
            for source, locations in source_pages.items():
                st.caption(f"`{source}` · {', '.join(locations)}")

        st.divider()
        st.caption(
            "Nothing leaves this machine. The app talks only to the local Ollama "
            "endpoint. Do not add private documents to a public repository."
        )

    # --------------------------------------------------------------------- main
    if not index_current:
        st.info("Build or rebuild the index from the sidebar before asking questions.")
    elif stats["chunks"] == 0:
        st.info("The index is empty. Add documents to `data/documents/` and build the index.")

    question = st.chat_input("Ask a question about the documents…")
    if question:
        if not index_current or stats["chunks"] == 0:
            st.error("Build the index first.")
        else:
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant"):
                with st.spinner("Retrieving evidence and generating an answer…"):
                    try:
                        result = pipeline.ask(question, top_k=top_k, threshold=threshold)
                    except Exception as error:  # noqa: BLE001
                        st.error(str(error))
                        st.stop()
                st.session_state["last_exchange"] = result
                render_answer(result)

    last = st.session_state.get("last_exchange")
    if last is not None and last.question != question:
        with st.chat_message("user"):
            st.markdown(last.question)
        with st.chat_message("assistant"):
            render_answer(last)

    with st.expander("How grounding and abstention work"):
        st.markdown(
            """
            The app embeds the question, retrieves the closest chunks and sends **only those
            chunks** to the local chat model. The prompt requires a citation for every factual
            statement. If no chunk passes the similarity threshold, or if the model returns an
            answer without a valid citation, the assistant replies that the documents do not
            contain enough information.

            The similarity threshold should be selected on the validation split with
            `eval/evaluate.py --tune-threshold`; the test split is only for the final report.
            """
        )


if __name__ == "__main__":
    main()
