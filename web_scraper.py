"""Web scraping utilities for the Dynamic Ollama Assistant."""

import logging
import re
from typing import Dict, List
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


def scrape_web_content(url: str, timeout: int = 10) -> Dict[str, str]:
    """
    Scrape text content from a single URL.
    
    Args:
        url: The URL to scrape
        timeout: Request timeout in seconds
        
    Returns:
        Dictionary with 'name', 'content', and 'url' keys
        
    Raises:
        requests.RequestException: If the request fails
        ValueError: If the URL is invalid or content cannot be parsed
    """
    if not url.strip():
        raise ValueError("URL cannot be empty")
    
    # Add protocol if missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove unwanted elements
        for tag in soup(['nav', 'footer', 'aside', 'script', 'style', 'header', 'menu']):
            tag.decompose()
        
        # Try to find main content area
        main_content = soup.find('main') or soup.find('article') or soup.find('div', class_=re.compile(r'content|main|body'))
        
        if main_content:
            text_content = main_content.get_text(separator='\n', strip=True)
        else:
            text_content = soup.get_text(separator='\n', strip=True)
        
        # Clean up the text
        lines = [line.strip() for line in text_content.split('\n') if line.strip()]
        clean_content = '\n'.join(lines)
        
        if not clean_content:
            raise ValueError("No readable content found on the page")
        
        # Get page title
        title = soup.find('title')
        page_title = title.get_text().strip() if title else urlparse(url).netloc
        
        return {
            'name': f"Web: {page_title}",
            'content': clean_content,
            'url': url
        }
        
    except requests.RequestException as e:
        raise requests.RequestException(f"Failed to fetch {url}: {str(e)}")
    except Exception as e:
        raise ValueError(f"Failed to parse content from {url}: {str(e)}")


def crawl_website(base_url: str, max_pages: int = 5, same_domain_only: bool = True) -> List[Dict[str, str]]:
    """
    Crawl multiple pages from a website.
    
    Args:
        base_url: Starting URL
        max_pages: Maximum number of pages to crawl
        same_domain_only: Only crawl pages from the same domain
        
    Returns:
        List of dictionaries with scraped content
    """
    if max_pages < 1:
        raise ValueError("max_pages must be at least 1")
    
    visited_urls = set()
    to_visit = [base_url]
    scraped_content = []
    base_domain = urlparse(base_url).netloc
    
    while to_visit and len(scraped_content) < max_pages:
        current_url = to_visit.pop(0)
        
        if current_url in visited_urls:
            continue
            
        visited_urls.add(current_url)
        
        try:
            # Scrape current page
            content = scrape_web_content(current_url)
            scraped_content.append(content)
            
            # Find more links if we haven't reached the limit
            if len(scraped_content) < max_pages:
                response = requests.get(current_url, timeout=10)
                soup = BeautifulSoup(response.content, 'html.parser')
                
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    full_url = urljoin(current_url, href)
                    
                    # Skip if same domain only is enabled and this is a different domain
                    if same_domain_only and urlparse(full_url).netloc != base_domain:
                        continue
                    
                    # Skip already visited or queued URLs
                    if full_url not in visited_urls and full_url not in to_visit:
                        to_visit.append(full_url)
                        
        except Exception as e:
            logging.warning(f"Failed to scrape {current_url}: {str(e)}")
            continue
    
    return scraped_content


def validate_url(url: str) -> bool:
    """
    Validate if a URL is properly formatted.
    
    Args:
        url: URL to validate
        
    Returns:
        True if URL is valid, False otherwise
    """
    try:
        if not url.strip():
            return False
        
        # Add protocol if missing for validation
        test_url = url if url.startswith(('http://', 'https://')) else 'https://' + url
        
        result = urlparse(test_url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False
