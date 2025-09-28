# Case Summarization Tool

A Flask web application for AI-powered case summarization that supports multiple file formats and can work with both LM Studio and Groq API.

## Features

- **Multiple Input Methods**: File upload (PDF, DOCX, TXT) and direct text input
- **File Support**: PDF, DOCX, and TXT files up to 20MB
- **Flexible API Integration**: Easy switching between LM Studio and Groq API
- **Modern UI**: Responsive design with drag-and-drop file upload
- **Configurable Summary Length**: Adjustable word count limits
- **Error Handling**: Comprehensive error handling and user feedback

## Prerequisites

- Python 3.7+
- LM Studio (for local inference) or Groq API key (for production)

## Installation

1. Clone or download the project files
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

### Using LM Studio (Default)

1. Install and run LM Studio
2. Load your preferred model in LM Studio
3. Ensure LM Studio is running on `http://localhost:1234`
4. The application is configured to use LM Studio by default

### Switching to Groq API

1. Get your Groq API key from [Groq Console](https://console.groq.com/)
2. Set the environment variable:
   ```bash
   export GROQ_API_KEY="your_groq_api_key_here"
   ```
3. In the `app.py` file, change the configuration:
   ```python
   # Change this line in the Config class
   API_PROVIDER = "groq"  # Change from "lm_studio" to "groq"
   ```

## Running the Application

### Development Mode
```bash
python app.py
```

### Production Mode
```bash
# Using Gunicorn (recommended for production)
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app

# Or using Flask's built-in server
export FLASK_APP=app.py
export FLASK_ENV=production
flask run --host=0.0.0.0 --port=5000
```

The application will be available at `http://localhost:5000`

## Usage

1. **File Upload**: 
   - Click "Choose File" or drag and drop supported files
   - Supported formats: PDF, DOCX, TXT (max 20MB)

2. **Text Input**: 
   - Switch to "Text Input" tab
   - Paste your case text directly

3. **Generate Summary**: 
   - Set desired maximum word count (100-2000)
   - Click "Generate Summary"
   - Copy the result using the "Copy Summary" button

## API Endpoints

- `GET /` - Main application interface
- `POST /summarize` - Generate summary (accepts file or text)
- `GET /health` - Health check endpoint
- `GET /config` - Configuration information

## File Structure

```
case-summarizer/
├── app.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── README.md          # This file
└── templates/         # (Optional) For external HTML templates
```

## Configuration Options

### Environment Variables
- `GROQ_API_KEY` - Your Groq API key (required when using Groq)

### Application Settings
- `MAX_CONTENT_LENGTH` - Maximum file size (default: 20MB)
- `API_PROVIDER` - Choose between "lm_studio" or "groq"
- `LM_STUDIO_BASE_URL` - LM Studio API endpoint (default: http://localhost:1234)
- `GROQ_MODEL` - Groq model to use (default: llama3-8b-8192)

## Customization

### Frontend Changes
The HTML template is embedded in the Python file for easy deployment. To customize:

1. Modify the `HTML_TEMPLATE` variable in `app.py`
2. Or extract it to a separate file in `templates/` directory and use `render_template()`

### API Provider Changes
The application uses a provider pattern for easy API switching:

1. Current providers: `LMStudioProvider` and `GroqProvider`
2. Add new providers by implementing the same interface
3. Update the `APIProvider.get_provider()` method

### Adding New File Formats
To support additional file formats:

1. Add extraction function (e.g., `extract_text_from_format()`)
2. Update `process_file()` function
3. Add the format to the frontend file picker

## Deployment

### Docker Deployment
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py .
EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
```

### Cloud Deployment
The application is ready for deployment on:
- Heroku
- AWS EC2/ECS
- Google Cloud Platform
- Azure App Service

## Security Considerations

1. **File Upload Security**: Files are processed in memory and not stored permanently
2. **API Keys**: Use environment variables for sensitive credentials
3. **Input Validation**: File size and type validation implemented
4. **Rate Limiting**: Consider adding rate limiting for production use

## Troubleshooting

### Common Issues

1. **LM Studio Connection Error**
   - Ensure LM Studio is running on localhost:1234
   - Check if a model is loaded in LM Studio

2. **File Upload Issues**
   - Verify file format is supported (PDF, DOCX, TXT)
   - Check file size is under 20MB
   - Ensure file is not corrupted

3. **Groq API Issues**
   - Verify API key is set correctly
   - Check API rate limits
   - Ensure model name is correct

## License

This project is open source and available under the [MIT License](LICENSE).

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review the configuration settings
3. Check the application logs for error details