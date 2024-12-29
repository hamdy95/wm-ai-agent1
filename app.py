import os
import re
import toml
import fitz  # PyMuPDF
import openai
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from typing import Dict, List, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# [Previous functions remain the same - extract_toc_and_sections, extract_section_with_gpt]

def perform_audit(iosa_checklist: str, input_text: str) -> str:
    """
    Perform an audit using GPT to evaluate compliance with ISARPs
    
    Args:
        iosa_checklist (str): The IOSA checklist standards to evaluate against
        input_text (str): The text to be evaluated
        airline_profile (str): The airline profile information
        
    Returns:
        str: Audit results including assessment, recommendations, and compliance scores
    """
    # Load the secrets from the toml file
    

    # Create the OpenAI client using the API key from secrets.toml
    client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    # OpenAI API request
    response = client.chat.completions.create(
        model='gpt-4o',
        messages=[
            {
                'role': 'system',
                'content': """
    You are an expert aviation auditor with over 20 years of experience in both business and commercial aviation...
    [Rest of the system message remains the same]
    """
            },
            {
                'role': 'user',
                'content': f"""
    OBJECTIVES:
    You are provided with a document and an input text...
    [Rest of the user message remains the same]
    
    ISARPs: 
    {iosa_checklist}

    INPUT_TEXT: 
    {input_text}
    """
            }
        ],
        max_tokens=4000
    )
    
    return response.choices[0].message.content

@app.route('/audit', methods=['POST'])
def conduct_audit():
    """
    API endpoint to perform aviation compliance audit
    """
    try:
        # Validate request data
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400
            
        data = request.json
        required_fields = ['iosa_checklist', 'input_text']
        
        # Check if all required fields are present
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({
                "error": f"Missing required fields: {', '.join(missing_fields)}"
            }), 400

        # Perform the audit
        audit_result = perform_audit(
            data['iosa_checklist'],
            data['input_text']
        )
        
        return jsonify({
            "message": "Audit completed successfully",
            "audit_result": audit_result
        }), 200
        
    except Exception as e:
        return jsonify({
            "error": f"Error performing audit: {str(e)}"
        }), 500
    

def extract_toc_and_sections(pdf_path: str, expand_pages: int = 7) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extract table of contents and sections from a PDF file
    
    Args:
        pdf_path (str): Path to the PDF file
        expand_pages (int, optional): Number of pages to expand for section extraction. Defaults to 7.
    
    Returns:
        Dict containing extracted sections
    """
    doc = fitz.open(pdf_path)
    toc = doc.get_toc()  # Extract the Table of Contents (TOC)
    sections = {}

    # Create a dictionary to map TOC entries to text in the PDF
    for toc_entry in toc:
        level, title, page = toc_entry
        try:
            # Extract text from the starting page and the following pages
            section_text = ""
            for i in range(page - 1, min(page - 1 + expand_pages + 1, len(doc))):
                page_text = doc.load_page(i).get_text("text")
                if not page_text:
                    page_text = doc.load_page(i).get_text("blocks")  # Try blocks if text is empty
                section_text += page_text if page_text else "Text not available for this section\n"
            
            # Check if the title already exists in sections, if so append to the list
            if title in sections:
                sections[title].append({
                    "level": level,
                    "page": page,
                    "text": section_text.strip()
                })
            else:
                sections[title] = [{
                    "level": level,
                    "page": page,
                    "text": section_text.strip()
                }]
        except Exception as e:
            if title in sections:
                sections[title].append({
                    "level": level,
                    "page": page,
                    "text": f"Error extracting text: {str(e)}"
                })
            else:
                sections[title] = [{
                    "level": level,
                    "page": page,
                    "text": f"Error extracting text: {str(e)}"
                }]

    # Function to detect section headers like "ORG 1.1.1", "ORG 2.3.4", etc.
    def find_section_headers(page_text):
        pattern = r'\b(ORG \d+(\.\d+){1,5})\b'  # Matches patterns like ORG 1.1, ORG 2.1.1, etc.
        headers = re.findall(pattern, page_text)
        return [header[0] for header in headers]

    # Scan each page for section headers not in the TOC
    for page_num in range(len(doc)):
        page_text = doc.load_page(page_num).get_text("text")
        headers = find_section_headers(page_text)

        for header in headers:
            # If header is not already in sections, add it
            section_text = ""
            for i in range(page_num, min(page_num + expand_pages + 1, len(doc))):
                page_text = doc.load_page(i).get_text("text")
                if not page_text:
                    page_text = doc.load_page(i).get_text("blocks")  # Try blocks if text is empty
                section_text += page_text if page_text else "Text not available for this section\n"
            
            # Append this occurrence of the header to the list in sections
            if header in sections:
                sections[header].append({
                    "level": header.count('.') + 1,  # Determine level by the number of dots
                    "page": page_num + 1,
                    "text": section_text.strip()
                })
            else:
                sections[header] = [{
                    "level": header.count('.') + 1,
                    "page": page_num + 1,
                    "text": section_text.strip()
                }]

    return sections

def extract_section_with_gpt(section_name: str, chunk_text: str) -> str:
    """
    Extract a specific section from text using GPT
    
    Args:
        section_name (str): Name of the section to extract
        chunk_text (str): Text chunk to extract from
    
    Returns:
        str: Extracted section text
    """
    # Initialize OpenAI client
    client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    # OpenAI API request
    response = client.chat.completions.create(
        model='gpt-4o',
        messages=[
            {
                'role': 'system',
                'content': (
                    """
    Context:
    You are tasked with extracting sections from a document. Your focus is on finding specific sections based on their header names and extracting only the relevant portion. Ignore any unrelated text that appears before or after the specified section. If you select a parent section, extract all its child sections. If it's a child without subchildren, extract only that section.
                    """
                )
            },
            {
                'role': 'user',
                'content': (
                    f"""
    OBJECTIVE:
    You are provided with the full text of a document. Your task is to extract the section titled "{section_name}". The section starts with this title and ends at the conclusion of the relevant content. Please extract and return only the content of the section titled "{section_name}".

    Here is the document text:
    {chunk_text}

    Extract and return only the content of the section titled "{section_name}". Do not include unrelated text.
                    """
                )
            }
        ],
        max_tokens=4000  # Adjust token limit based on document size
    )

    # Return the extracted section
    return response.choices[0].message.content

@app.route('/upload', methods=['POST'])
def upload_pdf():
    """
    API endpoint to upload PDF and extract sections
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            # Extract sections
            sections = extract_toc_and_sections(filepath)
            
            # Optional: Clean up the uploaded file
            os.remove(filepath)
            
            return jsonify({
                "message": "PDF processed successfully",
                "sections": sections
            }), 200
        
        except Exception as e:
            # Optional: Clean up the uploaded file
            if os.path.exists(filepath):
                os.remove(filepath)
            
            return jsonify({"error": str(e)}), 500

@app.route('/extract_section', methods=['POST'])
def extract_section():
    """
    API endpoint to extract a specific section
    """
    data = request.json
    
    if not data or 'section_name' not in data or 'text' not in data:
        return jsonify({"error": "Invalid request. Requires section_name and text"}), 400
    
    try:
        extracted_text = extract_section_with_gpt(
            data['section_name'], 
            data['text']
        )
        
        return jsonify({
            "section_name": data['section_name'],
            "extracted_text": extracted_text
        }), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint
    """
    return jsonify({"status": "healthy"}), 200

# Error Handlers
@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"error": "File too large"}), 413

@app.errorhandler(400)
def bad_request(error):
    return jsonify({"error": "Bad request"}), 400

@app.errorhandler(500)
def internal_server_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
