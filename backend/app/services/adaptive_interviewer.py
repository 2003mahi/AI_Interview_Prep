"""Adaptive AI Interviewer Service for AI Engineer and GenAI Roles.

Features:
- Personalized question generation for AI Engineer and GenAI roles.
- Topics covered: Technical, Python, RAG, LLM, Debugging, and System Design.
- Single-question progression with adaptive difficulty.
- Deep reasoning probing via targeted follow-ups.
- Strict duplicate question prevention (hash + token overlap).
- Robust LLM output validation (Pydantic + markdown stripper + JSON repair).
- Safe failure handling with comprehensive zero-credit/offline fallback question bank.
- Seamless pause, resume, and continuation from exact exit state.
"""

import hashlib
import json
import random
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar
from pydantic import BaseModel, ValidationError

from ..config import settings
from ..logger import logger
from ..schemas.interview import (
    CandidateAnswerRequest,
    DifficultyLevel,
    EvaluationResult,
    GeneratedQuestion,
    InteractionTurn,
    InterviewResponse,
    InterviewRole,
    InterviewSessionState,
    QuestionTopic,
    SessionStatus,
    StartInterviewRequest,
    compute_question_hash,
    normalize_question_text,
)

T = TypeVar("T", bound=BaseModel)


# ============================================================================
# CURATED HIGH-QUALITY QUESTION BANK (AI ENGINEER & GENAI ROLES)
# Used for safe fallback, zero-token operation, and offline reliability
# ============================================================================

CURATED_QUESTION_BANK: Dict[QuestionTopic, Dict[DifficultyLevel, List[Dict[str, Any]]]] = {
    QuestionTopic.PYTHON: {
        DifficultyLevel.JUNIOR: [
            {
                "text": "In Python, how do generator functions and the 'yield' statement work, and why are they preferable when streaming tokens or processing large text datasets compared to list comprehensions?",
                "context": "Building an API endpoint that streams LLM completions chunk by chunk.",
                "concepts": ["generators", "yield", "memory efficiency", "lazy evaluation", "streaming"],
                "criteria": ["Explains lazy evaluation vs loading entire payload into memory", "Describes how yield pauses function state", "Relates to memory footprint during large data batches"],
            },
            {
                "text": "What is the difference between shallow copy and deep copy in Python, and how might modifying nested dictionaries in prompt templates cause unexpected side effects across concurrent requests?",
                "context": "Prompt management where templates contain nested default parameters.",
                "concepts": ["copy module", "shallow copy", "deep copy", "mutable default arguments", "state isolation"],
                "criteria": ["Identifies nested reference sharing in shallow copy", "Explains mutation risks in multi-tenant or concurrent workflows", "Suggests copy.deepcopy or immutable structures"],
            },
        ],
        DifficultyLevel.MID: [
            {
                "text": "How does the Global Interpreter Lock (GIL) impact CPU-bound tokenization and vector operations versus I/O-bound LLM API calls in Python? When would you use asyncio vs multiprocessing?",
                "context": "A Python backend handling parallel vector embeddings and OpenAI API calls.",
                "concepts": ["GIL", "asyncio", "multiprocessing", "CPU-bound vs I/O-bound", "event loop"],
                "criteria": ["Differentiates CPU-bound (tokenization) from I/O-bound (HTTP calls)", "Explains asyncio cooperative multitasking for I/O", "Recommends multiprocessing or native extensions for CPU crunching"],
            },
            {
                "text": "How would you implement a custom context manager in Python to track, log, and strictly cap peak GPU/CPU memory allocation during batch inference with PyTorch?",
                "context": "Preventing Out-Of-Memory (OOM) crashes in production batch pipelines.",
                "concepts": ["__enter__", "__exit__", "torch.cuda.memory_allocated", "resource cleanup", "exceptions handling"],
                "criteria": ["Defines __enter__ and __exit__ correctly", "Demonstrates torch.cuda.empty_cache or memory snapshots", "Ensures cleanup even if exceptions occur during inference"],
            },
        ],
        DifficultyLevel.SENIOR: [
            {
                "text": "Explain how Python's garbage collection (reference counting + cyclic GC) behaves with large circular object graphs in machine learning models and caches. How do you profile and prevent memory leaks in long-running FastAPI inference workers?",
                "context": "FastAPI service experiencing slow memory growth after serving thousands of inference requests.",
                "concepts": ["gc module", "reference counting", "cyclic garbage collector", "tracemalloc", "weakref", "objgraph"],
                "criteria": ["Details reference counting limitations with cycles", "Explains tracemalloc or memory_profiler usage", "Discusses weakref or explicit cache eviction (LRU/TTL)"],
            },
            {
                "text": "How does PyTorch utilize zero-copy memory sharing with NumPy arrays and shared memory across multi-process DataLoader workers? What are the edge cases with file descriptor limits and CUDA IPC?",
                "context": "High-throughput training and inference data loader optimization.",
                "concepts": ["zero-copy", "shared memory", "torch.from_numpy", "CUDA IPC", "file descriptors"],
                "criteria": ["Explains shared memory buffer allocation", "Discusses torch.multiprocessing and IPC handles", "Identifies file descriptor exhaustion issues (ulimit) and mitigation"],
            },
        ],
        DifficultyLevel.LEAD: [
            {
                "text": "Design an ultra-low-latency asynchronous execution pipeline in Python for real-time bidirectional audio/text GenAI streaming (e.g. WebSocket). How do you eliminate event-loop starvation, manage task cancellation safely, and integrate C++/Rust extensions (pybind11/PyO3)?",
                "context": "Voice-to-voice conversational AI requiring sub-200ms glass-to-glass latency.",
                "concepts": ["asyncio task cancellation", "event-loop starvation", "PyO3", "C++ extensions", "zero-copy buffers"],
                "criteria": ["Addresses event loop blocking mitigation (run_in_executor / native threads)", "Handles CancelledError without leaking network or audio buffers", "Outlines zero-copy FFI bridge with Rust/C++"],
            },
        ],
    },
    QuestionTopic.RAG: {
        DifficultyLevel.JUNIOR: [
            {
                "text": "What is the difference between naive chunking (fixed character length) and semantic chunking in a Retrieval-Augmented Generation (RAG) pipeline? What issues arise when chunks split mid-sentence or mid-code-block?",
                "context": "Ingesting technical documentation and API specifications into a vector database.",
                "concepts": ["chunk size", "chunk overlap", "semantic boundary", "tokenization", "context preservation"],
                "criteria": ["Explains chunk size and overlap trade-offs", "Discusses broken semantic meaning and lost references", "Mentions recursive character splitting or AST-based splitting"],
            },
            {
                "text": "Explain the concept of cosine similarity versus euclidean distance when searching for relevant context in a vector database. Why is cosine similarity commonly used with normalized text embeddings?",
                "context": "Setting up similarity metric for Chroma/Qdrant collection.",
                "concepts": ["cosine similarity", "dot product", "l2 distance", "vector normalization", "embedding space"],
                "criteria": ["Explains angle vs magnitude distinction", "Notes that dot product equals cosine similarity when vectors are unit-normalized", "Identifies relevance to text length invariance"],
            },
        ],
        DifficultyLevel.MID: [
            {
                "text": "How does Hybrid Search (dense vector embeddings + sparse BM25/keyword search) work, and how does Reciprocal Rank Fusion (RRF) combine their scores? In what scenarios does dense search fail where sparse search succeeds?",
                "context": "Enterprise search over internal wikis containing acronyms, product IDs, and code snippets.",
                "concepts": ["hybrid search", "BM25", "dense embeddings", "Reciprocal Rank Fusion", "out-of-vocabulary terms"],
                "criteria": ["Explains BM25 exact term matching vs dense semantic matching", "Defines RRF rank aggregation formula and constant k", "Identifies failures with part numbers, serial codes, or rare domain jargon"],
            },
            {
                "text": "Explain how reranking models (e.g., cross-encoders like Cohere or BGE-Reranker) improve precision over bi-encoder vector retrieval. What is the latency and computational trade-off?",
                "context": "Improving Top-3 context retrieval quality for a high-stakes financial RAG application.",
                "concepts": ["bi-encoder", "cross-encoder", "full self-attention across query and passage", "latency trade-off", "two-stage retrieval"],
                "criteria": ["Explains cross-encoder token-level cross-attention", "Contrasts with bi-encoder independent representation dot product", "Justifies two-stage retrieval (retrieve top 50, rerank top 5) for latency"],
            },
        ],
        DifficultyLevel.SENIOR: [
            {
                "text": "Address the 'Lost in the Middle' phenomenon in long-context RAG. How do you architect context compression, parent-document retrieval, and metadata filtering to optimize token budget while maximizing recall?",
                "context": "A legal contract analysis assistant receiving 50 retrieved excerpts per query.",
                "concepts": ["Lost in the Middle", "parent-document retriever", "contextual compression", "metadata filtering", "token budgeting"],
                "criteria": ["Explains U-shaped recall curve in LLM attention over long prompts", "Describes parent-child chunking (retrieve small chunks, pass parent section)", "Details LLMLingua/selective compression to preserve critical clauses"],
            },
            {
                "text": "How do you systematically evaluate a production RAG system? Walk through the Ragas or TruLens metrics (Context Relevance, Groundedness/Faithfulness, Answer Relevance). How would you detect and alert on hallucination drift in production?",
                "context": "Monitoring quality for a customer-facing support RAG bot serving 100k daily queries.",
                "concepts": ["Ragas framework", "faithfulness", "answer relevance", "context precision/recall", "synthetic evaluation dataset", "LLM-as-a-judge calibration"],
                "criteria": ["Defines the core evaluation triad (faithfulness, answer relevance, context relevance)", "Explains sampling and LLM-as-a-judge calibration with ground truth", "Details automated production monitoring and threshold alerts"],
            },
        ],
        DifficultyLevel.LEAD: [
            {
                "text": "Architect an enterprise-scale Multimodal Graph-RAG system that ingests unstructured PDFs, financial tables, and relational knowledge graphs. How do you handle schema extraction, entity disambiguation, hybrid vector-graph traversal, and dynamic graph updates with zero downtime?",
                "context": "Global financial intelligence engine processing 10 million SEC filings and market news.",
                "concepts": ["GraphRAG", "knowledge graph extraction", "entity resolution", "community summaries", "vector + Cypher traversal", "real-time index updates"],
                "criteria": ["Describes community detection (Leiden/Louvain) for hierarchical summaries", "Outlines entity disambiguation pipeline across multimodal sources", "Details hybrid retrieval combining Cypher graph queries and vector nearest neighbors"],
            },
        ],
    },
    QuestionTopic.LLM: {
        DifficultyLevel.JUNIOR: [
            {
                "text": "Explain the role of temperature, top-p (nucleus sampling), and top-k in LLM text generation. When would you configure temperature close to 0 versus temperature = 0.8?",
                "context": "Configuring generation parameters for code generation vs creative writing.",
                "concepts": ["temperature", "top-p", "top-k", "logits", "softmax", "sampling"],
                "criteria": ["Explains logit scaling by temperature before softmax", "Contrasts deterministic output (code, extraction) with diverse output (creative)", "Defines top-p cumulative probability cutoff"],
            },
            {
                "text": "What is the difference between Few-Shot Prompting, Chain-of-Thought (CoT), and Zero-Shot prompting? Why does Chain-of-Thought improve reasoning in mathematical and multi-step tasks?",
                "context": "Building an automated unit test generator from business rules.",
                "concepts": ["zero-shot", "few-shot", "Chain-of-Thought", "intermediate reasoning tokens", "transformer autoregression"],
                "criteria": ["Explains that generating step-by-step tokens gives attention heads computation depth", "Provides concrete examples of input-output demonstrations", "Discusses prompt token overhead trade-offs"],
            },
        ],
        DifficultyLevel.MID: [
            {
                "text": "Compare Parameter-Efficient Fine-Tuning (PEFT/LoRA) with Full Fine-Tuning. How does low-rank matrix decomposition work (W = W0 + B * A), and what are the advantages regarding GPU VRAM and adapter swapping?",
                "context": "Customizing a 70B open-weights model for specialized biomedical entity extraction.",
                "concepts": ["LoRA", "PEFT", "rank r", "alpha scaling", "frozen weights", "multi-adapter serving"],
                "criteria": ["Explains rank r decomposition reducing trainable parameters by 99%+", "Calculates VRAM savings (avoiding full optimizer states for all weights)", "Explains dynamic adapter hot-swapping on a single base model in production"],
            },
            {
                "text": "What are the core differences between post-training quantization methods: AWQ (Activation-aware Weight Quantization), GPTQ, and GGUF? How do they affect inference latency, perplexity, and memory bandwidth?",
                "context": "Deploying Llama-3-70B onto cost-effective cloud GPU instances.",
                "concepts": ["quantization", "int4 vs fp16", "AWQ", "GPTQ", "GGUF", "memory bandwidth bound"],
                "criteria": ["Explains memory bandwidth bottleneck in autoregressive generation", "Identifies salient weight preservation in AWQ vs second-order error in GPTQ", "Contrasts GGUF CPU/Metal offloading with GPU-native kernels"],
            },
        ],
        DifficultyLevel.SENIOR: [
            {
                "text": "How does PagedAttention and Continuous Batching (as implemented in vLLM or TGI) solve memory fragmentation in the KV Cache? Calculate the KV Cache memory required for a 70B model with batch size 32 and context length 4096.",
                "context": "Sizing an enterprise LLM inference cluster to meet 50 requests/sec with minimal GPU count.",
                "concepts": ["PagedAttention", "continuous batching", "KV cache memory sizing", "memory fragmentation", "vLLM"],
                "criteria": ["Derives formula: 2 * num_layers * num_heads * head_dim * bytes_per_elem * batch * seq_len", "Explains continuous batching iteration-level scheduling instead of request-level padding", "Describes virtual memory paging analogy preventing static pre-allocation waste"],
            },
            {
                "text": "Compare Direct Preference Optimization (DPO), PPO (RLHF), and Kahneman-Tversky Optimization (KTO). Why has DPO largely replaced PPO for post-training alignment in open-source LLMs?",
                "context": "Aligning an internal coding assistant against developer feedback and security policies.",
                "concepts": ["RLHF", "PPO", "DPO", "implicit reward function", "Bradley-Terry model", "training stability"],
                "criteria": ["Explains analytic substitution of reward model into policy objective in DPO", "Highlights stability gains: no critic network, no value head, no complex PPO hyperparameters", "Discusses reference model drift and KL divergence constraint"],
            },
        ],
        DifficultyLevel.LEAD: [
            {
                "text": "Design an inference engine serving speculative decoding with a draft model and target model. Walk through the verification algorithm, tree-based speculative decoding, and the exact speedup conditions under memory-bound vs compute-bound constraints.",
                "context": "Optimizing a latency-critical coding auto-complete model to achieve 3x token generation speed.",
                "concepts": ["speculative decoding", "draft model", "acceptance probability", "rejection sampling", "Medusa / Eagle heads"],
                "criteria": ["Explains draft token generation followed by single forward-pass parallel verification", "Formulates modified acceptance criterion ensuring exact target distribution preservation", "Analyzes memory bandwidth vs compute utilization balance"],
            },
        ],
    },
    QuestionTopic.DEBUGGING: {
        DifficultyLevel.JUNIOR: [
            {
                "text": "Your FastAPI application calling an LLM API works fine locally for single requests, but under 20 concurrent users, requests begin timing out with 'HTTP 429 Too Many Requests'. Walk through how you diagnose and fix this.",
                "context": "Production incident report of cascading timeouts on an AI translation endpoint.",
                "concepts": ["HTTP 429", "rate limiting", "exponential backoff", "jitter", "token bucket", "connection pooling"],
                "criteria": ["Identifies provider rate limits (TPM / RPM)", "Implements exponential backoff with random jitter", "Mentions client-side queuing or distributed rate limiter (Redis)"],
            },
            {
                "text": "An LLM output parser expects a JSON schema, but the model intermittently wraps the response in markdown code blocks (```json ... ```) or includes conversational commentary ('Here is the JSON:'). How do you make the ingestion parser resilient?",
                "context": "Data extraction pipeline failing 5% of runs due to json.loads() JSONDecodeError.",
                "concepts": ["JSON parsing", "regex extraction", "markdown stripping", "Pydantic validation", "JSON repair"],
                "criteria": ["Extracts content inside backticks using regex or string splitting", "Applies json-repair or partial JSON decoders", "Enforces structured outputs (OpenAI json_object / json_schema mode) with fallback"],
            },
        ],
        DifficultyLevel.MID: [
            {
                "text": "During PyTorch fine-tuning with mixed precision (fp16/bf16), the training loss suddenly turns into 'NaN' at step 1400. How do you systematically isolate and resolve the root cause?",
                "context": "Fine-tuning a dense transformer model when loss collapses halfway through training.",
                "concepts": ["NaN loss", "gradient explosion", "gradient clipping", "fp16 dynamic loss scaling", "bf16 numerical stability", "learning rate warmup"],
                "criteria": ["Explains underflow/overflow in fp16 vs dynamic loss scaler", "Suggests switching to bf16 if hardware permits (larger dynamic range)", "Recommends gradient clipping, learning rate warmup, and checking for Inf/NaN in dataset"],
            },
            {
                "text": "Your autonomous LLM Agent enters an infinite loop, repeatedly calling the same search tool with minor keyword variations and consuming all API credits without reaching a final answer. How do you debug and architect hard guardrails to prevent this?",
                "context": "A customer research agent burning $400 in API credits on a single query.",
                "concepts": ["agent loop", "max iterations", "tool call deduplication", "reflection step", "circuit breaker", "state machine"],
                "criteria": ["Implements strict max_iterations and token budget limits", "Tracks history of tool calls with similarity hashing to detect looping", "Injects system steering prompt or triggers graceful fallback when cycle detected"],
            },
        ],
        DifficultyLevel.SENIOR: [
            {
                "text": "In a production RAG application, users report that for certain ambiguous queries, the system returns completely irrelevant citations, but when the exact query is tested in isolation, retrieval works. How would you diagnose whether this is caused by vector index stale updates, query rewriting hallucination, or metadata filtering bugs?",
                "context": "Intermittent retrieval quality bugs in an enterprise knowledge base with 2 million documents.",
                "concepts": ["query rewrite drift", "vector index sync lag", "metadata filter edge cases", "telemetry tracing", "embedding version mismatch"],
                "criteria": ["Establishes end-to-end tracing (Langfuse/OpenTelemetry) capturing raw query, rewritten query, and retrieved IDs", "Checks for embedding model mismatch between ingestion and query time", "Inspects metadata filter boolean logic and index replication lag"],
            },
            {
                "text": "A GPU inference node hosting a 70B parameter model triggers intermittent CUDA Out-Of-Memory (OOM) errors only when serving requests with long system prompts and sudden concurrency spikes. What profiling tools and architectural mitigations do you deploy?",
                "context": "Production vLLM instance crashing during morning traffic surge.",
                "concepts": ["CUDA OOM", "KV cache allocation", "vLLM max_model_len", "gpu_memory_utilization", "torch.cuda.memory_summary", "request queueing"],
                "criteria": ["Analyzes KV cache reservation vs model weight allocation (gpu_memory_utilization setting)", "Uses PyTorch memory profiler to inspect activation peaks vs cache", "Configures max_num_seqs and request queue admission control"],
            },
        ],
        DifficultyLevel.LEAD: [
            {
                "text": "Post-deployment of an updated fine-tuned model, automated benchmarks show a 40% degradation in safety alignment and subtle prompt injection vulnerability, while general coding benchmarks improved by 5%. How do you diagnose alignment tax/catastrophic forgetting and orchestrate a rollback and remediation strategy?",
                "context": "Urgent security finding: enterprise AI assistant leaking internal system prompts via indirect injection.",
                "concepts": ["catastrophic forgetting", "alignment tax", "indirect prompt injection", "adversarial red-teaming", "canary deployment", "KL regularization"],
                "criteria": ["Diagnoses overfitting or lack of alignment data replay in fine-tuning mixture", "Triggers immediate blue/green or canary rollback to previous vetted checkpoint", "Outlines retraining with safety replay buffer, KL penalty against base model, and automated adversarial red-team test suite"],
            },
        ],
    },
    QuestionTopic.SYSTEM_DESIGN: {
        DifficultyLevel.JUNIOR: [
            {
                "text": "Design a rate-limited, cached LLM gateway in front of multiple model providers (OpenAI, Anthropic, local model). What layers are required for request validation, caching identical queries, and monitoring token spend?",
                "context": "Internal platform team centralizing AI access for 15 engineering squads.",
                "concepts": ["API gateway", "exact match cache", "rate limiting", "token metering", "fallback provider"],
                "criteria": ["Designs cache using query + parameter hash (Redis)", "Explains token consumption tracking per user/team", "Outlines fallback routing when primary provider errors"],
            },
            {
                "text": "How do you design a secure Document Ingestion pipeline that allows users to upload resumes and job descriptions without exposing the backend to malware, zip bombs, or credential leakage in system prompts?",
                "context": "Resume analysis web application accepting PDF, DOCX, and TXT files.",
                "concepts": ["file validation", "magic bytes", "size limits", "virus scanning", "prompt injection sanitization"],
                "criteria": ["Validates MIME types via magic bytes not just extensions", "Imposes strict file size and decompression limits", "Sanitizes raw text to prevent prompt injection attacks"],
            },
        ],
        DifficultyLevel.MID: [
            {
                "text": "Design a Semantic Caching layer for an LLM customer service assistant. How do you compute similarity between incoming queries and cached queries, set similarity thresholds, and ensure stale data is invalidated when products or policies change?",
                "context": "Reducing LLM API costs by 40% on redundant customer queries (e.g. 'How do I return an item?').",
                "concepts": ["semantic cache", "vector distance threshold", "cache invalidation", "GPTCache / Redis", "false positive risk"],
                "criteria": ["Embeds incoming query and queries vector store for nearest neighbor above cosine threshold (e.g. 0.94)", "Discusses false positives where slight nuance changes meaning ('refund item' vs 'replace item')", "Details cache invalidation strategies (tagging, TTL, versioned namespaces)"],
            },
            {
                "text": "Design an asynchronous document parsing and embedding pipeline that can ingest 50,000 PDF documents (averaging 20 pages each) within 1 hour. Detail the message broker, worker pool, embedding batching, and database write strategies.",
                "context": "Enterprise client onboarding bulk migration.",
                "concepts": ["message queue (Celery/RabbitMQ/Kafka)", "worker scaling", "embedding batching", "vector DB bulk upsert", "idempotency"],
                "criteria": ["Partitions tasks by document/chunk into message queue", "Batches embedding calls (e.g., 256 chunks per batch) to maximize API/GPU throughput", "Uses vector database bulk upsert with idempotency keys"],
            },
        ],
        DifficultyLevel.SENIOR: [
            {
                "text": "Architect an end-to-end GenAI Coding Assistant with context awareness (repository-wide code search, AST symbol graphs, and real-time streaming suggestions). Address latency requirements (<200ms TTFT), security isolation, and context window assembly.",
                "context": "Building an in-house enterprise competitor to GitHub Copilot.",
                "concepts": ["repository indexing", "tree-sitter / AST", "Time-To-First-Token (TTFT)", "streaming WebSocket", "prompt packing", "local sandbox"],
                "criteria": ["Combines AST-based symbol definition lookup with vector retrieval for repository context", "Optimizes Time-To-First-Token via prompt caching and streaming chunk decoding", "Addresses intellectual property isolation and telemetry filtering"],
            },
            {
                "text": "Design a high-reliability Guardrail and Safety Filter architecture that inspects LLM inputs and outputs for PII, toxic content, and prompt injection in real time. How do you keep guardrail latency under 30ms without degrading user experience?",
                "context": "Regulated healthcare AI assistant communicating directly with patients.",
                "concepts": ["guardrails (NeMo / Llama Guard / Presidio)", "asynchronous parallel inspection", "PII masking", "low-latency small models", "regex/trie fast path"],
                "criteria": ["Uses fast-path regex/Aho-Corasick for deterministic PII/keywords", "Runs quantized lightweight classifier (e.g., DeBERTa-v3-small) in parallel or streaming pipeline", "Explains speculative streaming: stream tokens to client while verifying safety buffer"],
            },
        ],
        DifficultyLevel.LEAD: [
            {
                "text": "Design a global distributed Multi-Agent System where 50 autonomous agents collaborate to analyze market intelligence, execute code in secure sandboxes, and debate recommendations. Cover consensus protocols, Byzantine/hallucination fault tolerance, state persistence, and distributed tracing across async agent graphs.",
                "context": "Automated hedge fund investment research platform.",
                "concepts": ["multi-agent consensus", "secure sandbox (e.g., gVisor / Firecracker)", "distributed state machine", "graph orchestration (LangGraph)", "OpenTelemetry tracing"],
                "criteria": ["Details sandboxed execution isolation with strict resource and network boundaries", "Formulates multi-agent consensus or debate mechanism to cross-verify claims", "Architects state checkpointing for replaying or resuming interrupted agent graphs"],
            },
        ],
    },
    QuestionTopic.TECHNICAL: {
        DifficultyLevel.JUNIOR: [
            {
                "text": "What is the difference between supervised fine-tuning (SFT) and self-supervised pre-training in modern large language models? What data formats are required for each?",
                "context": "Explaining model lifecycle to a new AI engineer.",
                "concepts": ["pre-training", "SFT", "next-token prediction", "instruction tuning", "raw corpus vs prompt-response pairs"],
                "criteria": ["Explains next-token prediction over massive raw text corpus", "Contrasts with curated prompt-response pairs in SFT", "Discusses computational scale differences"],
            },
            {
                "text": "Explain how Positional Encodings work in the Transformer architecture. Why does a standard self-attention mechanism have no inherent sense of word order without them?",
                "context": "Reviewing core transformer mechanics.",
                "concepts": ["positional encoding", "self-attention permutation invariance", "sinusoidal vs learned", "RoPE", "token order"],
                "criteria": ["Explains permutation equivariance/invariance of self-attention dot product", "Describes how positional vectors inject token order", "Briefly contrasts absolute sinusoidal encodings with rotary positional embeddings (RoPE)"],
            },
        ],
        DifficultyLevel.MID: [
            {
                "text": "Walk through the mathematical mechanics of Multi-Head Attention vs Multi-Query Attention (MQA) and Grouped-Query Attention (GQA). Why have modern open-weight models (Llama 3, Mistral) transitioned to GQA?",
                "context": "Evaluating open-source base models for high-throughput deployment.",
                "concepts": ["Multi-Head Attention", "Multi-Query Attention", "Grouped-Query Attention", "KV cache size", "memory bandwidth"],
                "criteria": ["Explains separate Q, K, V heads in MHA", "Explains single K, V head shared across all Q heads in MQA", "Details GQA as balanced sweet spot (sharing KV heads across groups of Q heads) to slash KV cache while maintaining quality"],
            },
            {
                "text": "Explain how contrastive learning works in training text embedding models (e.g., InfoNCE loss). How do hard negatives and batch size affect representation quality in the embedding space?",
                "context": "Training custom domain embeddings for legal case retrieval.",
                "concepts": ["contrastive learning", "InfoNCE loss", "in-batch negatives", "hard negatives", "representation collapse"],
                "criteria": ["Formulates InfoNCE loss (maximizing positive pair cosine similarity vs negatives)", "Explains role of hard negatives (semantically similar but factually irrelevant documents)", "Notes impact of large batch sizes on negative diversity"],
            },
        ],
        DifficultyLevel.SENIOR: [
            {
                "text": "How does FlashAttention (1, 2, and 3) achieve a 3x-8x speedup and memory reduction in attention computation? Detail tiling, online softmax normalization, and IO-awareness across GPU SRAM vs HBM.",
                "context": "Profiling long-context training where standard attention runs out of SRAM.",
                "concepts": ["FlashAttention", "IO awareness", "SRAM vs HBM memory hierarchy", "tiling", "online softmax", "recomputation in backward pass"],
                "criteria": ["Explains memory bandwidth bottleneck reading/writing N x N attention matrix to HBM", "Details tiling query, key, value blocks into fast on-chip SRAM", "Explains online softmax scaling avoiding materialization of full attention matrix"],
            },
            {
                "text": "Compare Model Parallelism strategies: Tensor Parallelism (Megatron-LM), Pipeline Parallelism, and Fully Sharded Data Parallel (FSDP / ZeRO-3). For training a 100B parameter model across 64 GPUs, how would you hybridize these strategies?",
                "context": "Designing distributed training cluster layout on 8 nodes of 8xH100 GPUs.",
                "concepts": ["Tensor Parallelism", "Pipeline Parallelism", "FSDP / ZeRO-3", "intra-node NVLink", "inter-node InfiniBand", "all-reduce"],
                "criteria": ["Assigns Tensor Parallelism within node across fast NVLink (TP=8)", "Uses Pipeline Parallelism or FSDP across nodes over InfiniBand", "Explains communication overhead differences between TP all-reduce and ZeRO-3 all-gather"],
            },
        ],
        DifficultyLevel.LEAD: [
            {
                "text": "Analyze the scaling laws (Chinchilla compute-optimal training) and post-Chinchilla trends (inference-optimal overtraining, synthetic reasoning data, test-time compute scaling). How do you decide the capital allocation between pre-training compute, post-training RL, and test-time search (MCTS / best-of-N)?",
                "context": "Advising executive leadership on a $10M compute budget allocation for proprietary foundation models.",
                "concepts": ["Chinchilla scaling laws", "inference-optimal training", "test-time compute scaling", "process reward models", "MCTS / beam search", "compute budgeting"],
                "criteria": ["Explains Chinchilla compute ratio (tokens ~ 20x parameters) vs inference-optimal overtraining (Llama 3 15T tokens)", "Details test-time compute trade-offs (trading latency/tokens at inference for accuracy via PRMs / search)", "Provides structured capital allocation rationale based on target deployment volume"],
            },
        ],
    },
}


# ============================================================================
# ADAPTIVE INTERVIEWER ENGINE
# ============================================================================

class AdaptiveInterviewerService:
    """Manages adaptive interview generation, evaluation, probing, and session progression."""

    def __init__(self):
        self.max_probes_per_question = settings.__dict__.get("max_probes_per_question", 1)
        logger.info("Initialized AdaptiveInterviewerService with comprehensive AI/GenAI domain bank")

    def determine_difficulty(self, experience_years: int) -> DifficultyLevel:
        """Map experience years to targeted difficulty level."""
        if experience_years <= 1:
            return DifficultyLevel.JUNIOR
        elif experience_years <= 4:
            return DifficultyLevel.MID
        elif experience_years <= 8:
            return DifficultyLevel.SENIOR
        else:
            return DifficultyLevel.LEAD

    def is_duplicate(self, candidate_text: str, asked_questions: List[str], asked_hashes: List[str]) -> bool:
        """Check if candidate question is duplicate via exact hash or high lexical similarity."""
        candidate_hash = compute_question_hash(candidate_text)
        if candidate_hash in asked_hashes:
            return True

        norm_candidate = set(normalize_question_text(candidate_text).split())
        if not norm_candidate:
            return False

        for past_q in asked_questions:
            past_hash = compute_question_hash(past_q)
            if past_hash == candidate_hash:
                return True
            norm_past = set(normalize_question_text(past_q).split())
            if not norm_past:
                continue
            # Jaccard overlap check
            intersection = len(norm_candidate & norm_past)
            union = len(norm_candidate | norm_past)
            if union > 0 and (intersection / union) > 0.60:
                logger.warning(f"Duplicate question detected via token similarity: {candidate_text[:60]}...")
                return True

        return False

    def validate_llm_json(self, raw_content: str, model_class: Type[T]) -> Optional[T]:
        """Safely parse and validate LLM output into target Pydantic schema."""
        if not raw_content or not raw_content.strip():
            logger.warning("Empty LLM output received")
            return None

        # Clean markdown code blocks
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw_content.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
        cleaned = cleaned.strip()

        # Try direct JSON parsing
        try:
            data = json.loads(cleaned)
            return model_class.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning(f"Direct JSON parse failed: {e}. Attempting regex extraction.")

        # Fallback: regex search for outer JSON object
        match = re.search(r"(\{.*\})", cleaned, flags=re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                return model_class.model_validate(data)
            except Exception as e2:
                logger.error(f"Regex JSON fallback failed: {e2}")

        return None

    def get_fallback_question(
        self,
        topic: QuestionTopic,
        difficulty: DifficultyLevel,
        asked_questions: List[str],
        asked_hashes: List[str],
        role: str,
    ) -> GeneratedQuestion:
        """Retrieve a high-quality personalized question from curated bank without duplicating."""
        topic_pool = CURATED_QUESTION_BANK.get(topic, {})
        level_pool = topic_pool.get(difficulty, [])

        # If difficulty pool empty, fallback to MID or any available
        if not level_pool:
            level_pool = topic_pool.get(DifficultyLevel.MID, [])
        if not level_pool:
            for d in [DifficultyLevel.SENIOR, DifficultyLevel.JUNIOR, DifficultyLevel.LEAD]:
                if topic_pool.get(d):
                    level_pool = topic_pool[d]
                    break

        candidates = [q for q in level_pool if not self.is_duplicate(q["text"], asked_questions, asked_hashes)]

        # If all in level pool were asked, search other levels of this topic
        if not candidates:
            for other_diff, q_list in topic_pool.items():
                for q in q_list:
                    if not self.is_duplicate(q["text"], asked_questions, asked_hashes):
                        candidates.append(q)

        # Ultimate fallback if completely exhausted
        if not candidates:
            chosen = {
                "text": f"Explain your end-to-end approach to designing and optimizing production {topic.value.upper()} workflows for {role} positions, including error handling and latency bottlenecks.",
                "context": f"Practical architecture and implementation question for {role}.",
                "concepts": [topic.value, "scalability", "production reliability", "performance"],
                "criteria": ["Depth of explanation", "Concrete architectural choices", "Trade-off analysis"],
            }
        else:
            chosen = random.choice(candidates)

        q_text = str(chosen["text"])
        ctx = str(chosen["context"]) if chosen.get("context") else None
        concepts = [str(c) for c in chosen.get("concepts", [])]
        criteria = [str(c) for c in chosen.get("criteria", [])]

        return GeneratedQuestion(
            question_id=str(uuid.uuid4()),
            topic=topic,
            difficulty=difficulty,
            question_text=q_text,
            context_or_scenario=ctx,
            expected_concepts=concepts,
            key_evaluation_criteria=criteria,
            is_followup=False,
        )

    def generate_question(
        self,
        session_state: InterviewSessionState,
        topic: QuestionTopic,
    ) -> GeneratedQuestion:
        """Generate a personalized, validated question for the specified topic."""
        difficulty = self.determine_difficulty(session_state.experience_years)

        # If live OpenAI key is configured, we can attempt LLM generation with strict token budget
        # Otherwise or on any failure, smoothly use curated bank (zero credits, ultra fast)
        openai_key = getattr(settings, "openai_api_key", None)
        if openai_key and "placeholder" not in openai_key and len(openai_key) > 10:
            try:
                import httpx

                # Sanitize untrusted role string against prompt injection / control tokens
                clean_role = re.sub(r"[^\w\s\-/]", "", session_state.role).strip()[:60] or "AI Engineer"

                # Compact system prompt to minimize token consumption (< 100 tokens)
                sys_prompt = (
                    f"You are an expert AI Interviewer for {clean_role}. "
                    "Generate 1 rigorous, practical interview question in JSON format. "
                    "Return ONLY JSON matching schema: "
                    '{"question_text": str, "context_or_scenario": str, "expected_concepts": list[str], "key_evaluation_criteria": list[str]}'
                )
                user_prompt = (
                    f"Topic: {topic.value}. Difficulty: {difficulty.value}. "
                    f"Experience: {session_state.experience_years} yrs. "
                    f"Avoid duplicate topics from: {session_state.asked_questions[-2:]}."
                )

                response = httpx.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {openai_key}"},
                    json={
                        "model": getattr(settings, "llm_model", "gpt-4o-mini"),
                        "messages": [
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 250,
                    },
                    timeout=8.0,
                )
                if response.status_code == 200:
                    content = response.json()["choices"][0]["message"]["content"]
                    parsed = self.validate_llm_json(content, BaseModel)
                    if parsed and hasattr(parsed, "__dict__"):
                        data = parsed.model_dump() if hasattr(parsed, "model_dump") else parsed.__dict__
                        raw_q = data.get("question_text")
                        if raw_q and isinstance(raw_q, str) and not self.is_duplicate(raw_q, session_state.asked_questions, session_state.asked_question_hashes):
                            ctx_raw = data.get("context_or_scenario")
                            return GeneratedQuestion(
                                question_id=str(uuid.uuid4()),
                                topic=topic,
                                difficulty=difficulty,
                                question_text=raw_q,
                                context_or_scenario=str(ctx_raw) if ctx_raw else None,
                                expected_concepts=[str(c) for c in data.get("expected_concepts", [])],
                                key_evaluation_criteria=[str(c) for c in data.get("key_evaluation_criteria", [])],
                                is_followup=False,
                            )
            except Exception as e:
                logger.warning(f"LLM question generation failed: {e}. Falling back safely to domain question bank.")

        # Safe fallback: curated question bank
        return self.get_fallback_question(
            topic=topic,
            difficulty=difficulty,
            asked_questions=session_state.asked_questions,
            asked_hashes=session_state.asked_question_hashes,
            role=session_state.role,
        )

    def evaluate_answer(
        self,
        question: GeneratedQuestion,
        answer: str,
        role: str,
        is_probe_answer: bool = False,
    ) -> EvaluationResult:
        """Evaluate candidate answer for technical depth using multi-dimensional rubrics and determine reasoning probes."""
        from .rubric_evaluator import rubric_evaluator

        clean_answer = answer.strip()
        word_count = len(clean_answer.split())

        # Check for empty or trivial answers safely
        if word_count < 5:
            rubric_res = rubric_evaluator.evaluate(
                question_text=question.question_text,
                answer=answer,
                expected_concepts=question.expected_concepts,
                topic=question.topic.value if hasattr(question.topic, "value") else str(question.topic),
                role=role,
                context_or_scenario=question.context_or_scenario,
            )
            return EvaluationResult(
                score=rubric_res.overall_score,
                technical_accuracy="Very shallow or non-responsive answer.",
                strengths=[],
                weaknesses=["Answer lacks substantive technical content or explanation."],
                depth_score=10.0,
                should_probe=False,
                probe_reason=None,
                probe_question=None,
                feedback="Your response was too brief to evaluate technical understanding. Please explain the underlying mechanism.",
                rubric_evaluation=rubric_res,
                evidence=rubric_res.evidence,
                misconceptions=[m.explanation for m in rubric_res.misconceptions],
                corrections=rubric_res.corrections,
                next_exercises=[ex.model_dump() for ex in rubric_res.next_exercises],
                disclaimer=rubric_res.disclaimer,
            )

        # Run 5-dimension rubric evaluator
        rubric_res = rubric_evaluator.evaluate(
            question_text=question.question_text,
            answer=answer,
            expected_concepts=question.expected_concepts,
            topic=question.topic.value if hasattr(question.topic, "value") else str(question.topic),
            role=role,
            context_or_scenario=question.context_or_scenario,
        )

        base_score = rubric_res.overall_score
        depth_score = rubric_res.dimension_scores["conceptual_depth"].score

        # Determine if reasoning probe is warranted:
        should_probe = False
        probe_question = None
        probe_reason = None

        if not is_probe_answer and self.max_probes_per_question > 0:
            # Check for reasoning buzzwords without causal explanation
            buzzwords = ["vector", "rag", "lora", "cache", "asyncio", "vllm", "pagedattention", "embeddings", "bm25", "faiss"]
            found_buzzwords = [bw for bw in buzzwords if bw in clean_answer.lower()]
            has_causality = any(w in clean_answer.lower() for w in ["because", "therefore", "trade-off", "tradeoff", "bottleneck", "mitigate", "prevent", "in order to"])

            if found_buzzwords and not has_causality:
                should_probe = True
                probe_reason = f"Candidate mentioned {', '.join(found_buzzwords[:2])} but did not justify technical trade-offs or failure modes."
                probe_question = (
                    f"You highlighted using {found_buzzwords[0]}. What is the primary operational trade-off or failure mode "
                    f"with this approach, and how do you handle it in a high-concurrency production setting?"
                )
            elif word_count < 35 and base_score >= 40.0:
                should_probe = True
                probe_reason = "Answer is concise; probing for deeper architectural and practical reasoning."
                probe_question = (
                    f"Can you walk me through the underlying mechanism step-by-step for {question.topic.value}: "
                    f"specifically, what happens if this encounters edge-case constraints or scaling limits?"
                )

        feedback = (
            f"Demonstrated {('strong' if base_score >= 85 else 'solid' if base_score >= 70 else 'partial')} understanding of {question.topic.value}. "
            f"{rubric_res.criterion_feedback.technical_accuracy}"
        )

        return EvaluationResult(
            score=round(base_score, 1),
            technical_accuracy=rubric_res.criterion_feedback.technical_accuracy,
            strengths=rubric_res.strengths,
            weaknesses=rubric_res.areas_for_growth,
            depth_score=round(depth_score, 1),
            should_probe=should_probe,
            probe_reason=probe_reason,
            probe_question=probe_question,
            feedback=feedback,
            rubric_evaluation=rubric_res,
            evidence=rubric_res.evidence,
            misconceptions=[m.explanation for m in rubric_res.misconceptions],
            corrections=rubric_res.corrections,
            next_exercises=[ex.model_dump() for ex in rubric_res.next_exercises],
            disclaimer=rubric_res.disclaimer,
        )


    def start_session(self, user_id: str, request: StartInterviewRequest) -> InterviewSessionState:
        """Initialize an adaptive interview session and generate the initial question."""
        session_id = str(uuid.uuid4())
        topics = request.topics or [
            QuestionTopic.TECHNICAL,
            QuestionTopic.PYTHON,
            QuestionTopic.RAG,
            QuestionTopic.LLM,
            QuestionTopic.DEBUGGING,
            QuestionTopic.SYSTEM_DESIGN,
        ]

        total_q = min(request.total_questions, len(topics))

        state = InterviewSessionState(
            session_id=session_id,
            user_id=user_id,
            role=request.role,
            experience_years=request.experience_years,
            status=SessionStatus.IN_PROGRESS.value,
            target_topics=topics[:total_q],
            current_question_index=0,
            total_questions=total_q,
            current_question=None,
            current_probe=None,
            awaiting_probe=False,
            interactions=[],
            asked_questions=[],
            asked_question_hashes=[],
        )

        first_topic = state.target_topics[0]
        initial_question = self.generate_question(state, first_topic)
        state.current_question = initial_question
        state.asked_questions.append(initial_question.question_text)
        state.asked_question_hashes.append(compute_question_hash(initial_question.question_text))

        logger.info(f"Started adaptive interview session {session_id} for user {user_id} with topic {first_topic.value}")
        return state

    def submit_answer(
        self,
        session_state: InterviewSessionState,
        request: CandidateAnswerRequest,
    ) -> Tuple[InterviewSessionState, InterviewResponse]:
        """Process candidate answer, evaluate, probe reasoning if needed, or advance session."""
        if session_state.status != SessionStatus.IN_PROGRESS.value:
            # If session was paused, resume it on answer
            session_state.status = SessionStatus.IN_PROGRESS.value

        # Handle answer to follow-up probe
        if session_state.awaiting_probe and session_state.current_probe:
            probe_q = session_state.current_probe
            eval_result = self.evaluate_answer(
                question=probe_q,
                answer=request.answer,
                role=session_state.role,
                is_probe_answer=True,
            )

            # Update the last interaction turn with probe details
            if session_state.interactions:
                last_turn = session_state.interactions[-1]
                last_turn.probe_answer = request.answer
                last_turn.probe_score = eval_result.score
                last_turn.probe_feedback = eval_result.feedback
                # Blend scores: 60% base, 40% probe
                if last_turn.score is not None:
                    last_turn.score = round(0.6 * last_turn.score + 0.4 * eval_result.score, 1)

            session_state.awaiting_probe = False
            session_state.current_probe = None
            session_state.current_question_index += 1

            # Check if interview is completed
            if session_state.current_question_index >= session_state.total_questions:
                return self._finalize_session(session_state, eval_result)

            # Generate next topic question
            next_topic = session_state.target_topics[session_state.current_question_index]
            next_q = self.generate_question(session_state, next_topic)
            session_state.current_question = next_q
            session_state.asked_questions.append(next_q.question_text)
            session_state.asked_question_hashes.append(compute_question_hash(next_q.question_text))

            return session_state, InterviewResponse(
                session_id=session_state.session_id,
                status=session_state.status,
                current_question_index=session_state.current_question_index,
                total_questions=session_state.total_questions,
                is_probe=False,
                active_question=next_q,
                evaluation=eval_result,
                message="Follow-up probe recorded. Moving to next topic question.",
            )

        # Handle answer to base question
        active_q = session_state.current_question
        if not active_q:
            # Safe recovery: if no active question, generate one
            topic = session_state.target_topics[min(session_state.current_question_index, len(session_state.target_topics) - 1)]
            active_q = self.generate_question(session_state, topic)
            session_state.current_question = active_q

        eval_result = self.evaluate_answer(
            question=active_q,
            answer=request.answer,
            role=session_state.role,
            is_probe_answer=False,
        )

        turn = InteractionTurn(
            id=str(uuid.uuid4()),
            question_id=active_q.question_id,
            topic=active_q.topic.value,
            question=active_q.question_text,
            difficulty=active_q.difficulty.value,
            expected_concepts=active_q.expected_concepts,
            user_answer=request.answer,
            score=eval_result.score,
            feedback=eval_result.feedback,
            evaluation_details=eval_result.model_dump(),
        )
        session_state.interactions.append(turn)

        # If reasoning probe is triggered:
        if eval_result.should_probe and eval_result.probe_question:
            probe_question_obj = GeneratedQuestion(
                question_id=str(uuid.uuid4()),
                topic=active_q.topic,
                difficulty=active_q.difficulty,
                question_text=eval_result.probe_question,
                is_followup=True,
                parent_question_id=active_q.question_id,
                probe_reason=eval_result.probe_reason,
            )
            session_state.current_probe = probe_question_obj
            session_state.awaiting_probe = True
            turn.probe_question = eval_result.probe_question
            turn.probe_reason = eval_result.probe_reason

            return session_state, InterviewResponse(
                session_id=session_state.session_id,
                status=session_state.status,
                current_question_index=session_state.current_question_index,
                total_questions=session_state.total_questions,
                is_probe=True,
                active_question=probe_question_obj,
                evaluation=eval_result,
                message="Reasoning probe triggered to explore technical depth and trade-offs.",
            )

        # No probe needed: advance to next question
        session_state.current_question_index += 1

        if session_state.current_question_index >= session_state.total_questions:
            return self._finalize_session(session_state, eval_result)

        next_topic = session_state.target_topics[session_state.current_question_index]
        next_q = self.generate_question(session_state, next_topic)
        session_state.current_question = next_q
        session_state.asked_questions.append(next_q.question_text)
        session_state.asked_question_hashes.append(compute_question_hash(next_q.question_text))

        return session_state, InterviewResponse(
            session_id=session_state.session_id,
            status=session_state.status,
            current_question_index=session_state.current_question_index,
            total_questions=session_state.total_questions,
            is_probe=False,
            active_question=next_q,
            evaluation=eval_result,
            message="Answer evaluated. Moving to next question.",
        )

    def _finalize_session(
        self,
        session_state: InterviewSessionState,
        last_eval: EvaluationResult,
    ) -> Tuple[InterviewSessionState, InterviewResponse]:
        """Compute final aggregate scores and summary feedback."""
        session_state.status = SessionStatus.COMPLETED.value
        session_state.current_question = None
        session_state.current_probe = None
        session_state.awaiting_probe = False

        scores = [t.score for t in session_state.interactions if t.score is not None]
        avg_score = round(sum(scores) / max(1, len(scores)), 1) if scores else 0.0
        session_state.average_score = avg_score

        topics_covered = [t.topic for t in session_state.interactions]
        summary = (
            f"Adaptive interview completed for {session_state.role}. "
            f"Overall average score: {avg_score}%. "
            f"Topics evaluated: {', '.join(set(topics_covered))}. "
            f"{'Strong technical candidate recommended for advanced rounds.' if avg_score >= 75 else 'Candidate shows foundational knowledge with areas for deeper system-level preparation.'}"
        )
        session_state.summary_feedback = summary

        logger.info(f"Finalized interview session {session_state.session_id} with score {avg_score}%")

        return session_state, InterviewResponse(
            session_id=session_state.session_id,
            status=session_state.status,
            current_question_index=session_state.current_question_index,
            total_questions=session_state.total_questions,
            is_probe=False,
            active_question=None,
            evaluation=last_eval,
            average_score=avg_score,
            summary_feedback=summary,
            message="Interview session completed successfully.",
        )

    def resume_session(
        self,
        session_state: InterviewSessionState,
    ) -> Tuple[InterviewSessionState, InterviewResponse]:
        """Resume a session from where the candidate exited."""
        # Unpause if paused
        if session_state.status == SessionStatus.PAUSED.value:
            session_state.status = SessionStatus.IN_PROGRESS.value

        if session_state.status == SessionStatus.COMPLETED.value:
            return session_state, InterviewResponse(
                session_id=session_state.session_id,
                status=session_state.status,
                current_question_index=session_state.current_question_index,
                total_questions=session_state.total_questions,
                is_probe=False,
                active_question=None,
                average_score=session_state.average_score,
                summary_feedback=session_state.summary_feedback,
                message="This interview session is already completed.",
            )

        # Check if waiting for probe or base question
        if session_state.awaiting_probe and session_state.current_probe:
            active_q = session_state.current_probe
            is_probe = True
        else:
            active_q = session_state.current_question
            is_probe = False
            if not active_q and session_state.current_question_index < session_state.total_questions:
                topic = session_state.target_topics[session_state.current_question_index]
                active_q = self.generate_question(session_state, topic)
                session_state.current_question = active_q

        return session_state, InterviewResponse(
            session_id=session_state.session_id,
            status=session_state.status,
            current_question_index=session_state.current_question_index,
            total_questions=session_state.total_questions,
            is_probe=is_probe,
            active_question=active_q,
            message="Resumed session from exact previous state.",
        )


adaptive_interviewer = AdaptiveInterviewerService()
