import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "0"
import streamlit as st
import fitz  # PyMuPDF
import tempfile
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from retrieve_context import get_relevant_chunks, rerank_by_mnli
from generate_answer import (
    answer_with_context,
    summarize_document,
    summarize_by_sections,
    cloud_answer_with_context,
    cloud_summarize_document,
    cloud_summarize_by_sections,
)
from llm_provider import PROVIDER_PRESETS, detect_provider, get_llm_config

# Page configuration
st.set_page_config(
    page_title="CyberSec RAG Analyzer",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1f2937;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #6b7280;
        margin-bottom: 2rem;
    }
    .info-box {
        background-color: #f3f4f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #3b82f6;
        margin: 1rem 0;
    }
    .context-card {
        background-color: #ffffff;
        padding: 1.5rem;
        border-radius: 0.5rem;
        border: 1px solid #e5e7eb;
        margin: 1rem 0;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
        color: #1f2937;
    }
    .answer-box {
        background-color: #ecfdf5;
        padding: 1.5rem;
        border-radius: 0.5rem;
        border-left: 4px solid #10b981;
        margin: 1rem 0;
        color: #1f2937;
        font-size: 1.05rem;
        line-height: 1.6;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Helper functions for PDF processing
@st.cache_resource
def load_embedding_model():
    import torch
    try:
        # Force CPU and disable meta device
        torch.set_default_device('cpu')
        
        # Try loading with explicit parameters to avoid meta tensors
        model = SentenceTransformer(
            'all-MiniLM-L6-v2', 
            device='cpu',
            trust_remote_code=True,
            cache_folder=None
        )
        
        # Ensure model is on CPU and has real weights
        model = model.cpu()
        model.eval()
        
        # Test the model with a simple encoding
        test_embedding = model.encode(["test"], convert_to_numpy=True)
        if test_embedding is None or len(test_embedding) == 0:
            raise Exception("Model test encoding failed")
            
        return model
        
    except Exception as e:
        st.error(f"Error loading embedding model: {e}")
        
        # Try alternative approach with transformers directly
        try:
            from transformers import AutoTokenizer, AutoModel
            import torch.nn.functional as F
            
            # Load tokenizer and model separately
            tokenizer = AutoTokenizer.from_pretrained('sentence-transformers/all-MiniLM-L6-v2')
            model = AutoModel.from_pretrained(
                'sentence-transformers/all-MiniLM-L6-v2',
                dtype=torch.float32,
                device_map=None
            )
            model = model.cpu()
            model.eval()
            
            # Create a simple wrapper
            class SimpleEmbeddingModel:
                def __init__(self, tokenizer, model):
                    self.tokenizer = tokenizer
                    self.model = model
                    
                def encode(self, sentences, convert_to_numpy=True, show_progress_bar=False):
                    if isinstance(sentences, str):
                        sentences = [sentences]
                    
                    inputs = self.tokenizer(sentences, padding=True, truncation=True, return_tensors='pt')
                    
                    with torch.no_grad():
                        outputs = self.model(**inputs)
                        embeddings = outputs.last_hidden_state.mean(dim=1)
                    
                    if convert_to_numpy:
                        return embeddings.cpu().numpy()
                    return embeddings
            
            wrapper = SimpleEmbeddingModel(tokenizer, model)
            
            # Test the wrapper
            test_embedding = wrapper.encode(["test"], convert_to_numpy=True)
            if test_embedding is None or len(test_embedding) == 0:
                raise Exception("Wrapper test encoding failed")
                
            return wrapper
            
        except Exception as e2:
            st.error(f"Fallback model also failed: {e2}")
            
            # Last resort: try a different model
            try:
                model = SentenceTransformer(
                    'paraphrase-MiniLM-L6-v2',
                    device='cpu',
                    trust_remote_code=True
                )
                model = model.cpu()
                model.eval()
                return model
            except Exception as e3:
                st.error(f"All models failed to load: {e3}")
                return None

def chunk_text(text, chunk_size=400):
    """Split text into chunks by word count"""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunks.append(" ".join(words[i:i+chunk_size]))
    return chunks

def extract_text_from_pdf(pdf_file):
    """Extract text from uploaded PDF file"""
    try:
        # Check file size (limit to 50MB)
        if pdf_file.size > 50 * 1024 * 1024:
            st.error(f"File {pdf_file.name} is too large (>50MB). Please upload a smaller file.")
            return None
            
        # Save uploaded file to temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(pdf_file.read())
            tmp_path = tmp_file.name
        
        # Extract text using PyMuPDF
        doc = fitz.open(tmp_path)
        text = ""
        page_count = len(doc)
        
        if page_count == 0:
            st.warning(f"PDF {pdf_file.name} appears to be empty.")
            doc.close()
            os.unlink(tmp_path)
            return None
            
        for page_num, page in enumerate(doc):
            try:
                page_text = page.get_text()
                text += page_text + "\n"
            except Exception as e:
                st.warning(f"Could not extract text from page {page_num + 1} of {pdf_file.name}: {e}")
                continue
                
        doc.close()
        
        # Clean up temp file
        os.unlink(tmp_path)
        
        if not text.strip():
            st.warning(f"No text could be extracted from {pdf_file.name}. It might be a scanned PDF or image-based.")
            return None
            
        return text
        
    except Exception as e:
        st.error(f"Error extracting text from PDF {pdf_file.name}: {e}")
        return None

def process_uploaded_pdfs(uploaded_files):
    """Process uploaded PDFs and create embeddings"""
    try:
        model = load_embedding_model()
        if model is None:
            st.error("Could not load embedding model. Please try again.")
            return None, None, None, None
            
        all_chunks = []
        all_metadata = []
        processed_files = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, pdf_file in enumerate(uploaded_files):
            status_text.text(f"Processing {pdf_file.name}... ({idx + 1}/{len(uploaded_files)})")
            
            # Extract text
            text = extract_text_from_pdf(pdf_file)
            if text and text.strip():
                # Chunk the text
                chunks = chunk_text(text)
                if chunks:
                    for chunk in chunks:
                        if chunk.strip():  # Only add non-empty chunks
                            all_chunks.append(chunk)
                            all_metadata.append({"source": pdf_file.name})
                    processed_files.append(pdf_file.name)
                    st.success(f"✓ Processed {pdf_file.name}: {len(chunks)} chunks")
                else:
                    st.warning(f"No valid chunks created from {pdf_file.name}")
            else:
                st.warning(f"Could not extract meaningful text from {pdf_file.name}")
            
            progress_bar.progress((idx + 1) / len(uploaded_files))
        
        if not all_chunks:
            status_text.text("No valid content found in uploaded files.")
            st.error("No text content could be extracted from the uploaded PDFs.")
            progress_bar.empty()
            return None, None, None, None
        
        status_text.text(f"Creating embeddings for {len(all_chunks)} chunks...")
        
        try:
            # Create embeddings with error handling
            embeddings = model.encode(all_chunks, convert_to_numpy=True, show_progress_bar=False)
            
            # Create FAISS index
            dimension = embeddings.shape[1]
            index = faiss.IndexFlatL2(dimension)
            index.add(embeddings.astype(np.float32))
            
            status_text.empty()
            progress_bar.empty()
            
            st.success(f"Successfully processed {len(processed_files)} PDF(s) with {len(all_chunks)} text chunks")
            
            return index, all_chunks, all_metadata, model
            
        except Exception as e:
            st.error(f"Error creating embeddings: {e}")
            status_text.empty()
            progress_bar.empty()
            return None, None, None, None
            
    except Exception as e:
        st.error(f"Error processing PDFs: {e}")
        return None, None, None, None

def search_uploaded_docs(query, index, texts, metadata, model, top_k=3):
    """Search through uploaded documents"""
    try:
        if model is None:
            return []
            
        q_emb = model.encode([query], convert_to_numpy=True, show_progress_bar=False)
        q_emb = np.asarray(q_emb, dtype=np.float32)
        if q_emb.ndim == 1:
            q_emb = q_emb.reshape(1, -1)
        
        n = index.ntotal
        if n == 0:
            return []
        
        k = min(int(top_k), n)
        D, I = index.search(q_emb, k)
        return [(texts[i], metadata[i]) for i in I[0] if i >= 0 and i < len(texts)]
    except Exception as e:
        st.error(f"Error searching uploaded docs: {e}")
        return []

# Initialize session state
if 'uploaded_index' not in st.session_state:
    st.session_state.uploaded_index = None
if 'uploaded_texts' not in st.session_state:
    st.session_state.uploaded_texts = None
if 'uploaded_metadata' not in st.session_state:
    st.session_state.uploaded_metadata = None
if 'uploaded_model' not in st.session_state:
    st.session_state.uploaded_model = None
if 'uploaded_filenames' not in st.session_state:
    st.session_state.uploaded_filenames = []

# Sidebar with project information and upload
with st.sidebar:
    st.markdown("### About This Project")
    st.markdown("""
    **CyberSec RAG Analyzer** is a Retrieval-Augmented Generation system designed for 
    intelligent cybersecurity document analysis.
    """)
    
    st.markdown("---")
    st.markdown("### Upload PDFs")
    st.markdown("Upload your security reports for instant analysis:")
    
    uploaded_files = st.file_uploader(
        "Choose PDF files",
        type="pdf",
        accept_multiple_files=True,
        help="Upload one or more PDF files to analyze"
    )
    
    if uploaded_files:
        if st.button("Process Uploaded PDFs", type="primary", use_container_width=True):
            index, texts, metadata, model = process_uploaded_pdfs(uploaded_files)
            if index:
                st.session_state.uploaded_index = index
                st.session_state.uploaded_texts = texts
                st.session_state.uploaded_metadata = metadata
                st.session_state.uploaded_model = model
                st.session_state.uploaded_filenames = [f.name for f in uploaded_files]
                st.success(f"Processed {len(uploaded_files)} PDF(s) with {len(texts)} chunks")
            else:
                st.error("Failed to process PDFs. Please check the files.")
    
    if st.session_state.uploaded_filenames:
        st.markdown("**Currently loaded PDFs:**")
        for filename in st.session_state.uploaded_filenames:
            st.markdown(f"- {filename}")
        
        if st.button("Clear Uploaded PDFs", use_container_width=True):
            st.session_state.uploaded_index = None
            st.session_state.uploaded_texts = None
            st.session_state.uploaded_metadata = None
            st.session_state.uploaded_model = None
            st.session_state.uploaded_filenames = []
            st.rerun()
    
    st.markdown("---")
    st.markdown("### Technology Stack")
    st.markdown("""
    - **Semantic Search**: sentence-transformers (all-MiniLM-L6-v2)
    - **Vector Database**: FAISS (Facebook AI Similarity Search)
    - **Language Model**: BART (local) or Cloud LLM
    - **Reranker (optional)**: BART MNLI (facebook/bart-large-mnli)
    - **Framework**: Streamlit
    """)

    st.markdown("---")
    st.markdown("### Answer Generation")
    # Build provider options
    _provider_options = ["Local (BART)"]
    _provider_map = {"Local (BART)": None}
    for _pname, _preset in PROVIDER_PRESETS.items():
        _label = f"{_preset['display_name']} ({_preset['default_model']})"
        _provider_options.append(_label)
        _provider_map[_label] = _pname
    # Pre-select cloud provider when an API key is detected
    _detected = detect_provider()
    _default_idx = 0
    if _detected:
        for _i, _label in enumerate(_provider_options):
            if _provider_map.get(_label) == _detected:
                _default_idx = _i
                break
    selected_provider_label = st.selectbox(
        "LLM Provider",
        _provider_options,
        index=_default_idx,
        help="Choose the model used for answer generation and summarization.",
    )
    _selected_provider = _provider_map[selected_provider_label]
    llm_config = get_llm_config(provider=_selected_provider) if _selected_provider else None
    if _selected_provider and llm_config is None:
        st.warning(
            f"Set **{PROVIDER_PRESETS[_selected_provider]['env_key']}** "
            "environment variable to use this provider."
        )
    
    st.markdown("---")
    st.markdown("### How It Works")
    st.markdown("""
    1. **Document Processing**: Security reports are chunked and embedded
    2. **Semantic Retrieval**: Your query finds relevant document chunks
    3. **Answer Generation**: Local BART or cloud LLM generates contextual answers
    4. **Source Attribution**: View exact sources used
    """)
    
    st.markdown("---")
    st.markdown("### Features")
    st.markdown("""
    - Upload PDFs directly in the browser
    - Local processing (no external APIs)
    - Context-aware responses
    - Source transparency
    - Fast semantic search
    """)

# Main content
st.markdown('<p class="main-header">Cybersecurity Document Analyzer</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Ask questions or generate summaries of your security reports with AI-powered analysis</p>', unsafe_allow_html=True)

# Metrics row
col1, col2, col3, col4 = st.columns(4)
with col1:
    _model_label = llm_config.model if llm_config else "BART (Local)"
    st.metric("Model", _model_label, "Transformer-based")
with col2:
    st.metric("Search Method", "Semantic + optional rerank", "Vector similarity")
with col3:
    st.metric("Response Type", "Grounded", "Source-attributed")
with col4:
    doc_count = len(st.session_state.uploaded_filenames) if st.session_state.uploaded_filenames else 0
    st.metric("Uploaded Docs", doc_count, "Active")

st.markdown("---")

# Mode selection
mode = st.radio(
    "Choose analysis mode:",
    ["Q&A (Question & Answer)", "Document Summarization"],
    horizontal=True,
    help="Select whether to ask questions or generate document summaries"
)

if mode == "Q&A (Question & Answer)":
    # Query input for Q&A mode
    query = st.text_input(
        "Enter your cybersecurity question:",
        placeholder="e.g., What vulnerabilities were found in the firewall?",
        help="Ask any question about your indexed security documents"
    )
else:
    # Summarization mode
    query = None
    st.markdown("### Document Summarization")
    st.markdown("Generate summaries of your uploaded documents or existing indexed documents.")

if mode == "Q&A (Question & Answer)":
    # Search source selection for Q&A
    col_opt1, col_opt2, col_opt3 = st.columns(3)
    with col_opt1:
        search_existing = st.checkbox("Search existing documents", value=True, help="Search pre-indexed documents")
    with col_opt2:
        search_uploaded = st.checkbox(
            "Search uploaded PDFs", 
            value=True if st.session_state.uploaded_filenames else False,
            disabled=not st.session_state.uploaded_filenames,
            help="Search recently uploaded PDF documents"
        )
    with col_opt3:
        use_mnli_rerank = st.checkbox(
            "Enable MNLI reranking", 
            value=False,
            help="Rerank retrieved chunks by zero-shot entailment (BART MNLI)"
        )
else:
    # Summarization source selection
    col_sum1, col_sum2 = st.columns(2)
    with col_sum1:
        summarize_existing = st.checkbox(
            "Summarize existing documents", 
            value=False, 
            help="Generate summary from pre-indexed documents"
        )
    with col_sum2:
        summarize_uploaded = st.checkbox(
            "Summarize uploaded PDFs", 
            value=True if st.session_state.uploaded_filenames else False,
            disabled=not st.session_state.uploaded_filenames,
            help="Generate summary from recently uploaded PDF documents"
        )
    
    # Summarization options
    if summarize_uploaded or summarize_existing:
        col_sum_opt1, col_sum_opt2 = st.columns(2)
        with col_sum_opt1:
            summary_type = st.selectbox(
                "Summary type:",
                ["Full document summary", "Section-by-section summary"],
                help="Choose between a single summary or multiple section summaries"
            )
        with col_sum_opt2:
            summary_length = st.selectbox(
                "Summary length:",
                ["Short (150 words)", "Medium (300 words)", "Long (500 words)"],
                index=1,
                help="Choose the desired length of the summary"
            )
    
    # Set default values for Q&A variables in summarization mode
    search_existing = False
    search_uploaded = False
    use_mnli_rerank = False

col_btn1, col_btn2 = st.columns([1, 5])
with col_btn1:
    if mode == "Q&A (Question & Answer)":
        action_button = st.button("Analyze Query", type="primary", use_container_width=True)
    else:
        action_button = st.button("Generate Summary", type="primary", use_container_width=True)

if action_button and (query or mode == "Document Summarization"):
    if mode == "Q&A (Question & Answer)":
        # Q&A Mode
        with st.spinner("Analyzing security documents..."):
            all_chunks = []
            
            # Search existing documents
            if search_existing:
                try:
                    existing_chunks = get_relevant_chunks(query, top_k=3)
                    all_chunks.extend(existing_chunks)
                except Exception as e:
                    st.warning(f"Could not search existing documents: {e}")
            
            # Search uploaded documents
            if search_uploaded and st.session_state.uploaded_index:
                try:
                    uploaded_chunks = search_uploaded_docs(
                        query, 
                        st.session_state.uploaded_index,
                        st.session_state.uploaded_texts,
                        st.session_state.uploaded_metadata,
                        st.session_state.uploaded_model,
                        top_k=3
                    )
                    all_chunks.extend(uploaded_chunks)
                except Exception as e:
                    st.warning(f"Could not search uploaded documents: {e}")
            
            chunks = all_chunks
            
            # Optional MNLI reranking
            if chunks and use_mnli_rerank:
                try:
                    chunks = rerank_by_mnli(query, chunks, top_k=min(len(chunks), 10))
                except Exception as e:
                    st.warning(f"MNLI reranking skipped: {e}")
            
            if not chunks:
                if not search_existing and not search_uploaded:
                    st.warning("Please select at least one search source (existing documents or uploaded PDFs).")
                else:
                    st.warning("No relevant context found. Try uploading PDFs or ensure embeddings are built.")
                context = ""
            else:
                # Sort by relevance and limit to top results
                context = "\n\n".join([c[0] for c in chunks[:5]])
            
            try:
                answer = cloud_answer_with_context(context, query, llm_config)
            except Exception as e:
                answer = None
                st.error(f"Error generating answer: {e}")
    
    else:
        # Summarization Mode
        with st.spinner("Generating document summary..."):
            all_text_chunks = []
            
            # Get text from existing documents
            if summarize_existing:
                try:
                    # Get all chunks from existing documents (no query needed)
                    from retrieve_context import _load_resources
                    index, texts, metadata = _load_resources()
                    if texts is not None:
                        all_text_chunks.extend([t for t in texts if t.strip()])
                except Exception as e:
                    st.warning(f"Could not access existing documents: {e}")
            
            # Get text from uploaded documents
            if summarize_uploaded and st.session_state.uploaded_texts:
                all_text_chunks.extend([t for t in st.session_state.uploaded_texts if t.strip()])
            
            if not all_text_chunks:
                st.warning("No documents selected for summarization. Please upload PDFs or select existing documents.")
                summary_result = None
            else:
                # Parse summary length
                length_map = {
                    "Short (150 words)": 150,
                    "Medium (300 words)": 300,
                    "Long (500 words)": 500
                }
                max_length = length_map.get(summary_length, 300)
                
                try:
                    if summary_type == "Full document summary":
                        summary_result = cloud_summarize_document(all_text_chunks, max_length, llm_config)
                    else:
                        summary_result = cloud_summarize_by_sections(all_text_chunks, section_size=3, max_summary_length=max_length//2, llm_config=llm_config)
                except Exception as e:
                    summary_result = None
                    st.error(f"Error generating summary: {e}")
    
    if mode == "Q&A (Question & Answer)":
        # Display answer
        st.markdown("### Generated Answer")
        if answer:
            st.markdown(f'<div class="answer-box">{answer}</div>', unsafe_allow_html=True)
        else:
            st.error("Unable to generate an answer. Please try rephrasing your question.")
        
        # Display context sources
        if chunks:
            st.markdown("---")
            st.markdown("### Retrieved Context Sources")
            st.caption(f"Found {len(chunks)} relevant document chunks")
            
            for idx, (chunk_text, meta) in enumerate(chunks[:5], 1):
                src = meta.get('source', 'unknown') if isinstance(meta, dict) else 'unknown'
                
                # Determine if from uploaded or existing
                if st.session_state.uploaded_filenames and src in st.session_state.uploaded_filenames:
                    source_type = "Uploaded PDF"
                else:
                    source_type = "Existing Document"
                
                with st.expander(f"Source {idx}: {src} ({source_type})", expanded=(idx == 1)):
                    st.markdown(f'<div class="context-card">{chunk_text[:500]}...</div>', unsafe_allow_html=True)
                    st.caption(f"Source document: {src} | Type: {source_type}")
    
    else:
        # Display summary
        st.markdown("### Generated Summary")
        if summary_result:
            if isinstance(summary_result, list):
                # Section-by-section summaries
                for idx, section_summary in enumerate(summary_result, 1):
                    st.markdown(f"#### Section {idx} Summary")
                    st.markdown(f'<div class="answer-box">{section_summary}</div>', unsafe_allow_html=True)
            else:
                # Single document summary
                st.markdown(f'<div class="answer-box">{summary_result}</div>', unsafe_allow_html=True)
            
            # Display summary statistics
            st.markdown("---")
            st.markdown("### Summary Statistics")
            col_stat1, col_stat2, col_stat3 = st.columns(3)
            with col_stat1:
                st.metric("Source Chunks", len(all_text_chunks))
            with col_stat2:
                if isinstance(summary_result, list):
                    total_words = sum(len(s.split()) for s in summary_result)
                else:
                    total_words = len(summary_result.split())
                st.metric("Summary Words", total_words)
            with col_stat3:
                st.metric("Summary Type", summary_type.split()[0])
        else:
            st.error("Unable to generate a summary. Please check your document selection.")
elif query and not action_button and mode == "Q&A (Question & Answer)":
    st.info("Click 'Analyze Query' to search and generate an answer.")
elif mode == "Document Summarization" and not action_button:
    st.info("Select documents to summarize and click 'Generate Summary'.")
else:
    # Show helpful info when no query or action
    if not st.session_state.uploaded_filenames and mode == "Q&A (Question & Answer)":
        st.info("Upload PDF files using the sidebar to get started, or use the existing indexed documents.")
    elif not st.session_state.uploaded_filenames and mode == "Document Summarization":
        st.info("Upload PDF files using the sidebar to generate summaries, or use the existing indexed documents.")

# Footer
st.markdown("---")
st.caption("RAG-based Cybersecurity Analyzer | Q&A + Summarization | Powered by BART / MiniMax / OpenAI + FAISS + Sentence Transformers | Upload PDFs for instant analysis")
st.caption("Build by Ramakrushna")
