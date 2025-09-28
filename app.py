import os
import json
import requests
from flask import Flask, request, jsonify, Response, render_template
from werkzeug.utils import secure_filename
import PyPDF2
import docx
from io import BytesIO
import tempfile
import logging
from groq import Groq

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20MB max file size

# Configuration
class Config:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "groq-key-here")
    GROQ_MODEL = "llama-3.1-8b-instant"
    API_PROVIDER = "groq"
    ALLOWED_IPS = os.getenv("ALLOWED_IPS", "").split(",") if os.getenv("ALLOWED_IPS") else []
    RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "False").lower() == "true"

# Rate limiting
from collections import defaultdict
import time

rate_limit_storage = defaultdict(list)

def get_client_ip():
    forwarded_ip = request.headers.get('X-Forwarded-For')
    if forwarded_ip:
        return forwarded_ip.split(',')[0].strip()
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip
    return request.remote_addr

def check_rate_limit(ip, max_requests=10, window_seconds=60):
    if not Config.RATE_LIMIT_ENABLED:
        return True
    now = time.time()
    rate_limit_storage[ip] = [req_time for req_time in rate_limit_storage[ip] 
                             if now - req_time < window_seconds]
    if len(rate_limit_storage[ip]) >= max_requests:
        return False
    rate_limit_storage[ip].append(now)
    return True

def check_ip_whitelist(ip):
    if not Config.ALLOWED_IPS or not Config.ALLOWED_IPS[0]:
        return True
    return ip in Config.ALLOWED_IPS

# API Integration Layer
class APIProvider:
    @staticmethod
    def get_provider():
        return GroqProvider()

class GroqProvider:
    def __init__(self):
        self.client = Groq(api_key=Config.GROQ_API_KEY)
        self.model = Config.GROQ_MODEL
        self.api_key = Config.GROQ_API_KEY
        self.base_url = "https://api.groq.com/openai/v1"

    def get_intelligent_system_prompt(self, text):
        """Simplified system prompt for Indian legal documents"""
        return """You are a professional Indian legal summarizer trained in Income Tax, GST, and judicial orders. Your task is to summarize any Indian legal document in 2–3 concise paragraphs (target: 25–30% of original text length). Follow these strict rules:

1. Obey any user-provided instructions first (e.g., use of bullet points, single paragraph, structure). If none are given, follow the default structure below.

2. Structure:
   • Paragraph 1: Clearly state the type of legal proceeding (e.g., ITAT Order, High Court Judgment), parties involved (if named), jurisdiction or authority, and triggering event (e.g., search, notice, assessment, agreement).
   • Paragraph 2: Present the key legal issues, contentions, and statutory provisions involved (mention Sections, Rules, or Clauses).
   • Paragraph 3 (if necessary): Mention the outcome—final decision, relief granted/denied, directions or remand, and binding effect.

3. Style Guide:
   • Use formal Indian legal English.
   • Avoid headings, emojis, fillers, or commentary.
   • Use bullet points *only if required for clarity* (e.g., listing 2–3 legal findings or orders).
   • Do *not* fabricate, infer, or hallucinate any content not present in the original.
   • Always retain exact names, dates, section numbers, and legal conclusions.
   • IMPORTANT: Separate each paragraph with a blank line (double line break) for proper formatting.

Your summary must be concise, accurate, and legally compliant. Suitable for professional legal-tech use."""
    
    def summarize(self, text, max_length=500, custom_prompt=None):
        try:
            if not self.api_key or self.api_key == "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":
                logger.warning("Using default API key - please set GROQ_API_KEY environment variable")
            
            if not self.api_key:
                return "Error: Groq API key not configured"
            
            # Calculate target length (25-30% of original text)
            original_word_count = len(text.split())
            target_length = min(max_length, max(100, int(original_word_count * 0.275)))  # 27.5% average
            
            if custom_prompt:
                system_prompt = self.get_intelligent_system_prompt(text)
                prompt = f"""{custom_prompt}

INPUT TEXT:
{text}

RESPONSE (Summarize in approximately {target_length} words):"""
            else:
                system_prompt = self.get_intelligent_system_prompt(text)
                prompt = f"""Summarize the following Indian legal document in approximately {target_length} words (25-30% of original length).

INPUT TEXT:
{text}

SUMMARY:"""
            
            # Use the Groq client directly for streaming
            try:
                logger.info(f"Making Groq API call with model: {self.model}, target length: {target_length}")
                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=target_length * 2,  # Allow some buffer for response
                    stream=True
                )
                
                logger.info(f"Groq API call successful, response type: {type(completion)}")
                return completion
                
            except Exception as groq_error:
                logger.error(f"Groq client error: {str(groq_error)}")
                return f"Error: {str(groq_error)}"
                
        except Exception as e:
            logger.error(f"Groq summarization error: {str(e)}")
            return f"Error: {str(e)}"

# File processing utilities
def extract_text_from_pdf(file_content):
    try:
        pdf_file = BytesIO(file_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"PDF extraction error: {str(e)}")
        return f"Error extracting PDF: {str(e)}"

def extract_text_from_docx(file_content):
    try:
        doc_file = BytesIO(file_content)
        doc = docx.Document(doc_file)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"DOCX extraction error: {str(e)}")
        return f"Error extracting DOCX: {str(e)}"

def extract_text_from_txt(file_content):
    try:
        return file_content.decode('utf-8').strip()
    except UnicodeDecodeError:
        try:
            return file_content.decode('latin-1').strip()
        except Exception as e:
            logger.error(f"TXT extraction error: {str(e)}")
            return f"Error extracting TXT: {str(e)}"

def process_file(file):
    filename = secure_filename(file.filename)
    file_content = file.read()
    
    if len(file_content) > 20 * 1024 * 1024:
        return None, "File size exceeds 20MB limit"
    
    if filename.lower().endswith('.pdf'):
        text = extract_text_from_pdf(file_content)
    elif filename.lower().endswith('.docx'):
        text = extract_text_from_docx(file_content)
    elif filename.lower().endswith('.txt'):
        text = extract_text_from_txt(file_content)
    else:
        return None, "Unsupported file format. Please upload PDF, DOCX, or TXT files."
    
    return text, None

# Flask routes
@app.before_request
def security_check():
    client_ip = get_client_ip()
    
    if request.endpoint == 'health':
        return None
    
    if not check_ip_whitelist(client_ip):
        logger.warning(f"Access denied for IP: {client_ip}")
        return jsonify({"error": "Access denied"}), 403
    
    if not check_rate_limit(client_ip):
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        return jsonify({"error": "Rate limit exceeded"}), 429

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/summarize', methods=['POST'])
def summarize():
    try:
        max_length = int(request.form.get('max_length', 500))
        main_content = request.form.get('main_content', '').strip()
        text_content = ""
        custom_instructions = None
        
        # File and text processing logic
        if 'file' in request.files:
            file = request.files['file']
            if file.filename != '':
                text_content, error = process_file(file)
                if error:
                    return jsonify({"success": False, "error": error})
                
                if main_content:
                    custom_instructions = main_content
        
        elif main_content:
            instruction_keywords = ['focus on', 'extract', 'summarize', 'analyze', 'provide', 'list', 'identify', 'highlight', 'please', 'only', 'just']
            
            if (len(main_content) < 500 and 
                any(keyword in main_content.lower() for keyword in instruction_keywords) and
                not any(indicator in main_content.lower() for indicator in ['plaintiff', 'defendant', 'whereas', 'agreement', 'contract', 'case no', 'court', 'judgment'])):
                custom_instructions = main_content
                return jsonify({"success": False, "error": "Instructions provided but no document content found. Please attach a file or include document text."})
            else:
                text_content = main_content
                
                lines = main_content.split('\n')
                instruction_lines = []
                document_lines = []
                
                for line in lines:
                    line_lower = line.lower().strip()
                    if (line_lower.startswith(('focus on', 'extract', 'summarize', 'analyze', 'provide', 'list', 'identify', 'highlight', 'please')) or
                        'focus on' in line_lower or 'extract only' in line_lower or 'summarize in' in line_lower):
                        instruction_lines.append(line.strip())
                    elif line.strip():
                        document_lines.append(line)
                
                if instruction_lines and document_lines:
                    text_content = '\n'.join(document_lines)
                    custom_instructions = '\n'.join(instruction_lines)
        
        else:
            return jsonify({"success": False, "error": "No content provided"})
        
        if text_content.startswith("Error"):
            return jsonify({"success": False, "error": text_content})
        
        if len(text_content) < 50:
            return jsonify({"success": False, "error": "Text too short to summarize (minimum 50 characters)"})
        
        # AI provider logic
        provider = APIProvider.get_provider()
        
        if custom_instructions:
            summary_response = provider.summarize(text_content, max_length, custom_instructions)
        else:
            summary_response = provider.summarize(text_content, max_length)
        
        logger.info(f"Summary response type: {type(summary_response)}")
        
        # Handle string error response
        if isinstance(summary_response, str):
            return jsonify({"success": False, "error": summary_response})
        
        # Handle streaming response
        def generate():
            try:
                logger.info("Processing Groq streaming response")
                for chunk in summary_response:
                    if hasattr(chunk, 'choices') and chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, 'content') and delta.content:
                            # Preserve paragraph breaks by converting newlines to HTML breaks
                            content = delta.content.replace('\n\n', '<br><br>').replace('\n', '<br>')
                            yield f"data: {json.dumps({'content': content})}\n\n"
                
                yield f"data: {json.dumps({'done': True})}\n\n"
                logger.info("Streaming completed successfully")
                
            except Exception as e:
                logger.error(f"Streaming error: {str(e)}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        return Response(generate(), mimetype='text/event-stream', headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*'
        })
        
    except Exception as e:
        logger.error(f"Summarization error: {str(e)}")
        return jsonify({"success": False, "error": f"Server error: {str(e)}"})

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "api_provider": Config.API_PROVIDER})

@app.route('/config')
def config():
    return jsonify({
        "api_provider": Config.API_PROVIDER,
        "max_file_size": "20MB",
        "supported_formats": ["PDF", "DOCX", "TXT"]
    })

if __name__ == '__main__':
    if Config.ALLOWED_IPS:
        logger.info(f"IP whitelist enabled: {Config.ALLOWED_IPS}")
    if Config.RATE_LIMIT_ENABLED:
        logger.info("Rate limiting enabled: 10 requests per minute")
    
    debug_mode = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))
    
    logger.info(f"Starting server on {host}:{port}")
    logger.info(f"Debug mode: {debug_mode}")
    logger.info(f"API Provider: {Config.API_PROVIDER}")
    
    app.run(debug=debug_mode, host=host, port=port)
