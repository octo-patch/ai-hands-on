from functools import lru_cache
from transformers import BartForConditionalGeneration, BartTokenizer
import torch

MODEL_NAME = "facebook/bart-large-cnn"

@lru_cache(maxsize=1)
def _load_tokenizer():
    try:
        return BartTokenizer.from_pretrained(MODEL_NAME, local_files_only=False)
    except Exception:
        # Fallback to a smaller model if BART fails
        return BartTokenizer.from_pretrained("facebook/bart-base")

@lru_cache(maxsize=1)
def _load_model():
    try:
        # Force CPU usage and proper weight loading
        model = BartForConditionalGeneration.from_pretrained(
            MODEL_NAME, 
            dtype=torch.float32,
            device_map=None,
            local_files_only=False
        )
        model.eval()
        return model
    except Exception as e:
        print(f"Failed to load BART-large, trying BART-base: {e}")
        # Fallback to smaller model
        model = BartForConditionalGeneration.from_pretrained(
            "facebook/bart-base",
            dtype=torch.float32,
            device_map=None
        )
        model.eval()
        return model

def answer_with_context(context, question):
    try:
        tokenizer = _load_tokenizer()
        model = _load_model()
        
        # Ensure we have some context
        if not context or len(context.strip()) == 0:
            return "No relevant context found to answer the question."
        
        prompt = f"Context: {context}\n\nQuestion: {question}\n\nAnswer:"
        
        # Tokenize with proper error handling
        inputs = tokenizer(
            [prompt], 
            return_tensors="pt", 
            max_length=1024, 
            truncation=True,
            padding=True
        )
        
        # Generate with error handling
        with torch.no_grad():
            output_ids = model.generate(
                **inputs, 
                max_length=200, 
                num_beams=2,  # Reduced for stability
                do_sample=False,
                early_stopping=True,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id
            )
        
        # Decode the response
        response = tokenizer.decode(output_ids[0], skip_special_tokens=True)
        
        # Clean up the response (remove the prompt part)
        if "Answer:" in response:
            response = response.split("Answer:")[-1].strip()
        
        return response if response else "Unable to generate a meaningful answer."
        
    except Exception as e:
        print(f"Error in answer generation: {e}")
        return f"Error generating answer: {str(e)}"

def summarize_document(text_chunks, max_summary_length=300):
    """Summarize document chunks using BART.
    
    Args:
        text_chunks: List of text strings to summarize
        max_summary_length: Maximum length of the summary
    
    Returns:
        String containing the summary
    """
    try:
        tokenizer = _load_tokenizer()
        model = _load_model()
        
        if not text_chunks:
            return "No content available to summarize."
        
        # Combine chunks into a single text, respecting token limits
        combined_text = ""
        for chunk in text_chunks:
            test_text = combined_text + "\n\n" + chunk if combined_text else chunk
            # Check if adding this chunk would exceed token limit
            tokens = tokenizer.encode(test_text, add_special_tokens=False)
            if len(tokens) > 900:  # Leave room for special tokens
                break
            combined_text = test_text
        
        if not combined_text.strip():
            return "No meaningful content found to summarize."
        
        # Tokenize for summarization
        inputs = tokenizer(
            [combined_text],
            return_tensors="pt",
            max_length=1024,
            truncation=True,
            padding=True
        )
        
        # Generate summary
        with torch.no_grad():
            summary_ids = model.generate(
                **inputs,
                max_length=max_summary_length,
                min_length=50,
                num_beams=4,
                do_sample=False,
                early_stopping=True,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id
            )
        
        # Decode summary
        summary = tokenizer.decode(summary_ids[0], skip_special_tokens=True)
        
        return summary if summary.strip() else "Unable to generate a meaningful summary."
        
    except Exception as e:
        print(f"Error in summarization: {e}")
        return f"Error generating summary: {str(e)}"

def summarize_by_sections(text_chunks, section_size=3, max_summary_length=200):
    """Summarize document by sections for better coverage of large documents.

    Args:
        text_chunks: List of text strings
        section_size: Number of chunks per section
        max_summary_length: Maximum length per section summary

    Returns:
        List of summaries, one per section
    """
    try:
        if not text_chunks:
            return ["No content available to summarize."]

        summaries = []
        for i in range(0, len(text_chunks), section_size):
            section_chunks = text_chunks[i:i+section_size]
            section_summary = summarize_document(section_chunks, max_summary_length)
            summaries.append(section_summary)

        return summaries

    except Exception as e:
        print(f"Error in section summarization: {e}")
        return [f"Error generating section summary: {str(e)}"]


# ---------------------------------------------------------------------------
# Cloud LLM answer generation (MiniMax / OpenAI / any OpenAI-compatible API)
# ---------------------------------------------------------------------------

def cloud_answer_with_context(context, question, llm_config=None):
    """Generate an answer using a cloud LLM provider.

    Falls back to :func:`answer_with_context` (local BART) when no
    *llm_config* is supplied.

    Parameters
    ----------
    context : str
        Retrieved document passages concatenated as context.
    question : str
        The user's question.
    llm_config : llm_provider.LLMConfig, optional
        Cloud LLM configuration.  When ``None`` the local BART model is used.

    Returns
    -------
    str
        The generated answer.
    """
    if llm_config is None:
        return answer_with_context(context, question)

    from llm_provider import chat_completion

    if not context or len(context.strip()) == 0:
        return "No relevant context found to answer the question."

    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful cybersecurity analyst. Answer the user's "
                "question based ONLY on the provided context. If the context "
                "does not contain enough information, say so clearly. Be "
                "concise and precise."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Context:\n{context}\n\n"
                f"Question: {question}\n\n"
                "Answer the question using only the context above."
            ),
        },
    ]

    try:
        return chat_completion(llm_config, messages)
    except Exception as e:
        print(f"Cloud LLM error, falling back to local BART: {e}")
        return answer_with_context(context, question)


def cloud_summarize_document(text_chunks, max_summary_length=300, llm_config=None):
    """Summarize document chunks using a cloud LLM provider.

    Falls back to :func:`summarize_document` (local BART) when no
    *llm_config* is supplied.

    Parameters
    ----------
    text_chunks : list[str]
        Text passages to summarise.
    max_summary_length : int
        Approximate word budget for the summary.
    llm_config : llm_provider.LLMConfig, optional
        Cloud LLM configuration.

    Returns
    -------
    str
        The generated summary.
    """
    if llm_config is None:
        return summarize_document(text_chunks, max_summary_length)

    from llm_provider import chat_completion

    if not text_chunks:
        return "No content available to summarize."

    combined = "\n\n".join(chunk for chunk in text_chunks if chunk.strip())
    # Truncate to ~12 000 chars to stay within typical context limits
    if len(combined) > 12000:
        combined = combined[:12000] + "\n...(truncated)"

    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful cybersecurity analyst. Summarize the "
                "document content below clearly and concisely."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Please summarize the following document in approximately "
                f"{max_summary_length} words:\n\n{combined}"
            ),
        },
    ]

    try:
        return chat_completion(llm_config, messages)
    except Exception as e:
        print(f"Cloud LLM error, falling back to local BART: {e}")
        return summarize_document(text_chunks, max_summary_length)


def cloud_summarize_by_sections(
    text_chunks, section_size=3, max_summary_length=200, llm_config=None
):
    """Summarize document by sections using a cloud LLM provider.

    Parameters
    ----------
    text_chunks : list[str]
        Text passages.
    section_size : int
        Number of chunks per section.
    max_summary_length : int
        Approximate word budget per section summary.
    llm_config : llm_provider.LLMConfig, optional
        Cloud LLM configuration.

    Returns
    -------
    list[str]
        One summary string per section.
    """
    if llm_config is None:
        return summarize_by_sections(text_chunks, section_size, max_summary_length)

    if not text_chunks:
        return ["No content available to summarize."]

    summaries = []
    for i in range(0, len(text_chunks), section_size):
        section = text_chunks[i : i + section_size]
        summaries.append(
            cloud_summarize_document(section, max_summary_length, llm_config)
        )
    return summaries
