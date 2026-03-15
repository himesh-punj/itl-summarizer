"""
Legal Document Summarizer — Security-Hardened Version
═════════════════════════════════════════════════════
Fixes applied:
  SUM-01: Removed hardcoded Groq API key from source code
  SUM-02: Removed hardcoded Groq key as fallback default
  SUM-03: Flask SECRET_KEY from env var (no hardcoded default)
  SUM-04: Rate limiter with memory bounds + eviction
  SUM-05: CORS whitelist (no wildcard *)
  SUM-06: Optional API key auth on /summarize endpoint
  SUM-07: Trusted proxy IP extraction (no blind X-Forwarded-For trust)
"""

import os
import json
import logging
from flask import Flask, request, jsonify, Response, render_template
from werkzeug.utils import secure_filename
import PyPDF2
import docx
from io import BytesIO
from groq import Groq

# ── Security imports ───────────────────────────────────────────────────────
from security_config import (
    get_validated_config, require_api_key, RateLimiter,
    get_trusted_ip, setup_cors, setup_security_headers,
    validate_file_extension, validate_text_length, sanitize_text,
    safe_log_config, ALLOWED_FILE_EXTENSIONS, MAX_TEXT_LENGTH
)

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Load and validate config (fails fast if env vars missing) ──────────────
CONFIG = get_validated_config("summarizer")

app = Flask(__name__)

# SUM-03: Secure secret key from validated env
app.config['SECRET_KEY'] = CONFIG['FLASK_SECRET_KEY']
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20MB

# SUM-05: CORS whitelist
setup_cors(app, CONFIG['CORS_ORIGINS'])
setup_security_headers(app)

# SUM-04: Rate limiter with memory bounds
rate_limiter = RateLimiter(
    max_requests=int(os.getenv("SUMMARIZER_RATE_LIMIT", "10")),
    window_seconds=int(os.getenv("SUMMARIZER_RATE_WINDOW", "60"))
)

# SUM-06: API key for auth
API_KEY = CONFIG.get('API_AUTH_KEY')

# IP whitelist (optional)
ALLOWED_IPS = [ip.strip() for ip in os.getenv("ALLOWED_IPS", "").split(",") if ip.strip()]


# ══════════════════════════════════════════════════════════════════════════
# GROQ PROVIDER — SUM-01/02: No hardcoded API keys anywhere
# ══════════════════════════════════════════════════════════════════════════

class GroqProvider:
    def __init__(self):
        # SUM-01/02: Key ONLY from validated env — no fallback defaults
        self.api_key = CONFIG['SUMMARIZER_GROQ_API_KEY']
        self.model = os.getenv("SUMMARIZER_GROQ_MODEL", "llama-3.1-8b-instant")
        self.client = Groq(api_key=self.api_key)
        self.base_url = "https://api.groq.com/openai/v1"

    def get_system_prompt(self):
        return """You are a professional Indian legal summarizer trained in Income Tax, GST, and judicial orders. Your task is to summarize any Indian legal document in 2-3 concise paragraphs (target: 25-30% of original text length). Follow these strict rules:

1. Obey any user-provided instructions first. If none are given, follow the default structure below.

2. Structure:
   Paragraph 1: Type of proceeding, parties, jurisdiction, triggering event.
   Paragraph 2: Key legal issues, contentions, statutory provisions.
   Paragraph 3 (if necessary): Outcome, relief, directions, binding effect.

3. Style Guide:
   Use formal Indian legal English.
   Avoid headings, emojis, fillers, or commentary.
   Use bullet points only when essential for clarity.
   Never fabricate or infer content not in the original.
   Retain exact names, dates, section numbers, and legal conclusions.
   Separate paragraphs with blank lines."""

    def summarize(self, text, max_length=500, custom_prompt=None):
        try:
            original_word_count = len(text.split())
            target_length = min(max_length, max(100, int(original_word_count * 0.275)))

            system_prompt = self.get_system_prompt()

            if custom_prompt:
                prompt = f"""{custom_prompt}

INPUT TEXT:
{text}

RESPONSE (Summarize in approximately {target_length} words):"""
            else:
                prompt = f"""Summarize the following Indian legal document in approximately {target_length} words (25-30% of original length).

INPUT TEXT:
{text}

SUMMARY:"""

            logger.info(f"Groq API call: model={self.model}, target_length={target_length}")

            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=target_length * 2,
                stream=True
            )

            return completion

        except Exception as e:
            logger.error(f"Groq error: {e}")
            return f"Error: {e}"


# ══════════════════════════════════════════════════════════════════════════
# FILE PROCESSING — same logic, cleaner error handling
# ══════════════════════════════════════════════════════════════════════════

def extract_text_from_pdf(file_content):
    try:
        pdf_reader = PyPDF2.PdfReader(BytesIO(file_content))
        return "\n".join(page.extract_text() or "" for page in pdf_reader.pages).strip()
    except Exception as e:
        logger.error(f"PDF extraction: {e}")
        return f"Error extracting PDF: {e}"


def extract_text_from_docx(file_content):
    try:
        doc = docx.Document(BytesIO(file_content))
        return "\n".join(p.text for p in doc.paragraphs).strip()
    except Exception as e:
        logger.error(f"DOCX extraction: {e}")
        return f"Error extracting DOCX: {e}"


def extract_text_from_txt(file_content):
    try:
        return file_content.decode('utf-8').strip()
    except UnicodeDecodeError:
        try:
            return file_content.decode('latin-1').strip()
        except Exception as e:
            return f"Error extracting TXT: {e}"


def process_file(file):
    """SEC-09: Validate extension before processing."""
    filename = secure_filename(file.filename)

    if not validate_file_extension(filename):
        return None, f"Unsupported file type. Allowed: {', '.join(ALLOWED_FILE_EXTENSIONS)}"

    file_content = file.read()

    if len(file_content) > 20 * 1024 * 1024:
        return None, "File size exceeds 20MB limit"

    ext = os.path.splitext(filename)[1].lower()
    if ext == '.pdf':
        text = extract_text_from_pdf(file_content)
    elif ext == '.docx':
        text = extract_text_from_docx(file_content)
    elif ext == '.txt':
        text = extract_text_from_txt(file_content)
    else:
        return None, "Unsupported format"

    return text, None


# ══════════════════════════════════════════════════════════════════════════
# MIDDLEWARE — SUM-04/07: Rate limiting with safe IP extraction
# ══════════════════════════════════════════════════════════════════════════

@app.before_request
def security_check():
    if request.endpoint == 'health':
        return None

    client_ip = get_trusted_ip(CONFIG['TRUSTED_PROXY_COUNT'])

    # IP whitelist check (if configured)
    if ALLOWED_IPS and client_ip not in ALLOWED_IPS:
        logger.warning(f"Blocked IP: {client_ip}")
        return jsonify({"error": "Access denied"}), 403

    # Rate limiting
    if not rate_limiter.check(client_ip):
        retry = rate_limiter.get_retry_after(client_ip)
        logger.warning(f"Rate limited: {client_ip}")
        return jsonify({
            "error": "Rate limit exceeded",
            "retry_after_seconds": retry
        }), 429


# ══════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/summarize', methods=['POST'])
@require_api_key(API_KEY)
def summarize():
    try:
        max_length = int(request.form.get('max_length', 500))
        # Cap max_length to prevent abuse
        max_length = min(max_length, 2000)

        main_content = request.form.get('main_content', '').strip()
        text_content = ""
        custom_instructions = None

        # File processing
        if 'file' in request.files:
            file = request.files['file']
            if file.filename:
                text_content, error = process_file(file)
                if error:
                    return jsonify({"success": False, "error": error})
                if main_content:
                    custom_instructions = main_content

        elif main_content:
            # SEC-10: Validate input length
            length_err = validate_text_length(main_content, MAX_TEXT_LENGTH)
            if length_err:
                return jsonify({"success": False, "error": length_err})

            instruction_keywords = ['focus on', 'extract', 'summarize', 'analyze', 'provide',
                                    'list', 'identify', 'highlight', 'please', 'only', 'just']

            legal_indicators = ['plaintiff', 'defendant', 'whereas', 'agreement',
                                'contract', 'case no', 'court', 'judgment']

            if (len(main_content) < 500 and
                any(kw in main_content.lower() for kw in instruction_keywords) and
                not any(ind in main_content.lower() for ind in legal_indicators)):
                return jsonify({
                    "success": False,
                    "error": "Instructions provided but no document content found. Please attach a file or include document text."
                })
            else:
                text_content = main_content

                # Separate instructions from content
                lines = main_content.split('\n')
                instruction_lines = []
                document_lines = []

                for line in lines:
                    line_lower = line.lower().strip()
                    if any(line_lower.startswith(kw) or kw in line_lower
                           for kw in ['focus on', 'extract only', 'summarize in']):
                        instruction_lines.append(line.strip())
                    elif line.strip():
                        document_lines.append(line)

                if instruction_lines and document_lines:
                    text_content = '\n'.join(document_lines)
                    custom_instructions = '\n'.join(instruction_lines)
        else:
            return jsonify({"success": False, "error": "No content provided"})

        # Sanitize
        text_content = sanitize_text(text_content)

        if text_content.startswith("Error"):
            return jsonify({"success": False, "error": text_content})

        if len(text_content) < 50:
            return jsonify({"success": False, "error": "Text too short (minimum 50 characters)"})

        # Generate summary
        provider = GroqProvider()

        if custom_instructions:
            # SEC-10: Sanitize and cap instruction length
            custom_instructions = sanitize_text(custom_instructions)[:2000]
            summary_response = provider.summarize(text_content, max_length, custom_instructions)
        else:
            summary_response = provider.summarize(text_content, max_length)

        # Handle error string
        if isinstance(summary_response, str):
            return jsonify({"success": False, "error": summary_response})

        # SUM-05: Streaming response with proper CORS (handled by setup_cors)
        def generate():
            try:
                for chunk in summary_response:
                    if hasattr(chunk, 'choices') and chunk.choices:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, 'content') and delta.content:
                            content = delta.content.replace('\n\n', '<br><br>').replace('\n', '<br>')
                            yield f"data: {json.dumps({'content': content})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
            except Exception as e:
                logger.error(f"Streaming error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return Response(generate(), mimetype='text/event-stream', headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            # SUM-05: No more Access-Control-Allow-Origin: * — handled by setup_cors
        })

    except Exception as e:
        logger.error(f"Summarization error: {e}")
        return jsonify({"success": False, "error": "Server error"})


@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "service": "legal-summarizer",
        "api_provider": "groq"
    })


@app.route('/config')
def config_info():
    return jsonify({
        "api_provider": "groq",
        "max_file_size": "20MB",
        "supported_formats": ["PDF", "DOCX", "TXT"],
        "rate_limit": f"{rate_limiter.max_requests} req / {rate_limiter.window}s"
    })


# ══════════════════════════════════════════════════════════════════════════
# MAIN — SUM-03: No hardcoded debug=True
# ══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    safe_log_config(CONFIG, "Legal Document Summarizer")

    debug = CONFIG.get('DEBUG', False)
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("SUMMARIZER_PORT", "5000"))

    if debug:
        logger.warning("DEBUG MODE IS ON — Do NOT use in production!")

    logger.info(f"Starting on {host}:{port}")
    app.run(debug=debug, host=host, port=port)
