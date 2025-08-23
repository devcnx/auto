"""
File handling utilities for the Dynamic Ollama Assistant GUI.

This module contains file processing and content extraction functions.
"""

import json
import logging
import os
import pandas as pd
from docling.document_converter import DocumentConverter


def process_uploaded_file(file_path):
    """Process an uploaded file and extract its content."""
    try:
        # Use Docling for document conversion
        converter = DocumentConverter()
        result = converter.convert(file_path)
        
        if result and result.document:
            # Get the markdown content
            content = result.document.export_to_markdown()
            
            if content and content.strip():
                return {
                    "name": f"Uploaded: {os.path.basename(file_path)}",
                    "content": content,
                    "file_path": file_path
                }
        
        # Fallback to manual processing
        return _fallback_file_processing(file_path)
        
    except Exception as e:
        logging.warning(f"Docling conversion failed for {file_path}: {e}")
        return _fallback_file_processing(file_path)


def _fallback_file_processing(file_path):
    """Fallback file processing when Docling fails."""
    content_parts = []
    
    # Text file fallback
    if file_path.lower().endswith(('.txt', '.md', '.py', '.js', '.html', '.css')):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            if content.strip():
                content_parts.append(content)
        except Exception as e:
            logging.warning(f"Text fallback failed for {file_path}: {e}")
    
    # CSV fallback
    if not content_parts and file_path.lower().endswith('.csv'):
        try:
            df = pd.read_csv(file_path)
            preview = df.head(500)
            md = preview.to_markdown(index=False)
            content_parts.append(f"# CSV Preview (first 500 rows)\n\n{md}")
        except Exception as e:
            logging.warning(f"CSV fallback failed for {file_path}: {e}")
    
    # JSON fallback
    if not content_parts and file_path.lower().endswith('.json'):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list) and data and isinstance(data[0], dict):
                df = pd.DataFrame(data)
                preview = df.head(500)
                md = preview.to_markdown(index=False)
                content_parts.append(f"# JSON Table Preview (first 500 rows)\n\n{md}")
            else:
                pretty = json.dumps(data, indent=2, ensure_ascii=False)[:200000]
                content_parts.append(f"```json\n{pretty}\n```")
        except Exception as e:
            logging.warning(f"JSON fallback failed for {file_path}: {e}")
    
    if content_parts:
        return {
            "name": f"Uploaded: {os.path.basename(file_path)}",
            "content": "\n\n".join(content_parts),
            "file_path": file_path
        }
    
    return {
        "name": f"Error: {os.path.basename(file_path)}",
        "content": f"Failed to process file: {file_path}",
        "file_path": file_path
    }


def validate_url(url):
    """Validate if a URL is properly formatted."""
    if not url or url.strip() == "":
        return False
    
    url = url.strip()
    return url.startswith(('http://', 'https://'))


def aggregate_parsed_content(parsed_files):
    """Aggregate content from multiple parsed files."""
    if not parsed_files:
        return None
    
    aggregated = []
    for file_data in parsed_files:
        name = file_data.get("name", "Unknown")
        content = file_data.get("content", "")
        
        if content:
            aggregated.append(f"## {name}\n\n{content}")
    
    return "\n\n---\n\n".join(aggregated) if aggregated else None
