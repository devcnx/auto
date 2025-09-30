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
    logging.info(f"Starting file processing for: {file_path}")
    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
    logging.info(f"File size: {file_size:,} bytes")
    
    try:
        # Use Docling for document conversion
        logging.info("Initializing Docling DocumentConverter...")
        converter = DocumentConverter()
        logging.info(f"Converting document: {os.path.basename(file_path)}")
        result = converter.convert(file_path)
        logging.info("Document conversion completed")
        
        if result and result.document:
            logging.info("Document conversion successful, extracting markdown content...")
            # Get the markdown content
            content = result.document.export_to_markdown()
            
            if content and content.strip():
                content_length = len(content)
                logging.info(f"Successfully extracted {content_length:,} characters of content")
                return {
                    "name": f"Uploaded: {os.path.basename(file_path)}",
                    "content": content,
                    "file_path": file_path
                }
            else:
                logging.warning("Docling conversion returned empty content")
        
        # Fallback to manual processing
        logging.info("Docling conversion did not return usable content, falling back to manual processing")
        return _fallback_file_processing(file_path)
        
    except Exception as e:
        logging.warning(f"Docling conversion failed for {file_path}: {e}")
        logging.info("Attempting fallback file processing...")
        return _fallback_file_processing(file_path)


def _fallback_file_processing(file_path):
    """Fallback file processing when Docling fails."""
    logging.info(f"Starting fallback processing for: {os.path.basename(file_path)}")
    content_parts = []
    
    # Text file fallback
    if file_path.lower().endswith(('.txt', '.md', '.py', '.js', '.html', '.css')):
        logging.info("Processing as text file...")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            if content.strip():
                logging.info(f"Successfully read {len(content):,} characters from text file")
                content_parts.append(content)
            else:
                logging.warning("Text file appears to be empty")
        except Exception as e:
            logging.warning(f"Text fallback failed for {file_path}: {e}")
    
    # CSV fallback
    if not content_parts and file_path.lower().endswith('.csv'):
        logging.info("Processing as CSV file...")
        try:
            df = pd.read_csv(file_path)
            total_rows = len(df)
            logging.info(f"CSV file contains {total_rows:,} rows and {len(df.columns)} columns")
            preview = df.head(500)
            md = preview.to_markdown(index=False)
            content_parts.append(f"# CSV Preview (first 500 rows)\n\n{md}")
            logging.info(f"Successfully processed CSV preview with {len(preview)} rows")
        except Exception as e:
            logging.warning(f"CSV fallback failed for {file_path}: {e}")
    
    # JSON fallback
    if not content_parts and file_path.lower().endswith('.json'):
        logging.info("Processing as JSON file...")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list) and data and isinstance(data[0], dict):
                logging.info(f"JSON contains {len(data)} records, converting to table format")
                df = pd.DataFrame(data)
                preview = df.head(500)
                md = preview.to_markdown(index=False)
                content_parts.append(f"# JSON Table Preview (first 500 rows)\n\n{md}")
                logging.info(f"Successfully processed JSON table with {len(preview)} rows")
            else:
                logging.info("JSON contains non-tabular data, formatting as pretty-printed JSON")
                pretty = json.dumps(data, indent=2, ensure_ascii=False)[:200000]
                content_parts.append(f"```json\n{pretty}\n```")
                logging.info(f"Successfully processed JSON content ({len(pretty):,} characters)")
        except Exception as e:
            logging.warning(f"JSON fallback failed for {file_path}: {e}")
    
    if content_parts:
        total_content = "\n\n".join(content_parts)
        logging.info(f"Fallback processing successful - extracted {len(total_content):,} characters total")
        return {
            "name": f"Uploaded: {os.path.basename(file_path)}",
            "content": total_content,
            "file_path": file_path
        }
    
    logging.error(f"All processing methods failed for: {file_path}")
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
