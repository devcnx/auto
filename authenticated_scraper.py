"""Authenticated web scraping with AI-assisted element detection."""

import asyncio
import json
import logging
import os
from typing import Dict, Optional, List
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page, Browser

from dynamic_ollama_assistant import query_ollama_chat_for_gui, DEFAULT_MODEL


class AuthenticatedScraper:
    """Handle authenticated web scraping with session management."""

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.sessions_file = "scraper_sessions.json"

    async def __aenter__(self):
        """Async context manager entry."""
        playwright = await async_playwright().__aenter__()
        self.browser = await playwright.chromium.launch(headless=False)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.browser:
            await self.browser.close()

    def analyze_login_form(self, html_content: str) -> Dict[str, str]:
        """Use AI to identify login form elements."""
        # Truncate HTML to avoid token limits
        html_snippet = html_content[:8000]

        prompt = f"""Analyze this HTML and identify login form elements. Look for username/email fields, password fields, and submit buttons.

HTML:
{html_snippet}

Return ONLY a JSON object with CSS selectors in this exact format:
{{"username": "css_selector_for_username", "password": "css_selector_for_password", "submit": "css_selector_for_submit_button"}}

Use specific selectors like input[type="email"], input[name="username"], #password, etc. If you can't find clear login elements, return {{"error": "No login form detected"}}.
"""

        try:
            response = "".join(
                query_ollama_chat_for_gui(
                    model=DEFAULT_MODEL,
                    system_prompt="You are a web scraping expert. Analyze HTML and return only valid JSON with CSS selectors.",
                    user_msg=prompt,
                    conversation_history=[],
                )
            )
            # Extract JSON from response - improved parsing
            response = response.strip()

            # Remove markdown code blocks
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                if end != -1:
                    response = response[start:end]
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                if end != -1:
                    response = response[start:end]

            # Try to find JSON object in the response
            response = response.strip()

            # Look for JSON object pattern
            import re

            if json_match := re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", response):
                response = json_match.group()

            # Clean up common JSON syntax errors
            response = re.sub(r'"\s*\)\s*}', '"}', response)  # Fix ")}" -> "}"
            response = re.sub(r'"\s*\)\s*,', '",', response)  # Fix ")," -> ","
            response = re.sub(r'"\s*\)\s*"', '""', response)  # Fix ")" -> ""

            # Parse JSON
            selectors = json.loads(response)

            # Validate the response format
            if isinstance(selectors, dict):
                return selectors
            else:
                return {"error": "Invalid response format from AI"}

        except json.JSONDecodeError as e:
            logging.error(f"JSON parsing error in login form analysis: {e}")
            logging.error(f"Raw response: {response}")
            return {"error": f"Failed to parse AI response as JSON: {str(e)}"}
        except Exception as e:
            logging.error(f"Failed to analyze login form: {e}")
            return {"error": f"Analysis failed: {str(e)}"}

    async def scrape_with_login(
        self,
        url: str,
        username: str,
        password: str,
        login_selectors: Optional[Dict[str, str]] = None,
        save_session: bool = True,
    ) -> Dict[str, str]:
        """Scrape content from a site requiring authentication."""

        if not self.browser:
            raise RuntimeError("Browser not initialized. Use async context manager.")

        page = await self.browser.new_page()

        try:
            # Navigate to the site
            await page.goto(url, wait_until="networkidle")

            # If no selectors provided, try to detect them
            if not login_selectors:
                html_content = await page.content()
                login_selectors = self.analyze_login_form(html_content)

                if "error" in login_selectors:
                    return {
                        "name": f"Error: {urlparse(url).netloc}",
                        "content": f"Failed to detect login form: {login_selectors['error']}",
                        "url": url,
                    }

            # Attempt login
            try:
                # Fill username with fallback options
                username_filled = False
                username_selectors = [
                    login_selectors["username"],
                    "input[type='email']",
                    "input[name='email']",
                    "input[name='username']",
                    "input[name='user']",
                    "#email",
                    "#username",
                    "#user"
                ]
                
                for selector in username_selectors:
                    try:
                        await page.fill(selector, username, timeout=3000)
                        username_filled = True
                        break
                    except Exception:
                        continue
                
                if not username_filled:
                    return {
                        "name": f"Login Error: {urlparse(url).netloc}",
                        "content": f"Could not find username field. Tried: {', '.join(username_selectors[:3])}",
                        "url": url,
                    }
                
                # Fill password with fallback options
                password_filled = False
                password_selectors = [
                    login_selectors["password"],
                    "input[type='password']",
                    "input[name='password']",
                    "input[name='pass']",
                    "#password",
                    "#pass",
                    "#passwd"
                ]
                
                for selector in password_selectors:
                    try:
                        await page.fill(selector, password, timeout=3000)
                        password_filled = True
                        break
                    except Exception:
                        continue
                
                if not password_filled:
                    return {
                        "name": f"Login Error: {urlparse(url).netloc}",
                        "content": f"Could not find password field. Tried: {', '.join(password_selectors[:3])}",
                        "url": url,
                    }
                
                # Try to submit the login form
                submit_result = await self._try_submit_button(page, login_selectors)
                if submit_result:  # If there was an error
                    return submit_result

                # Wait for navigation or content change
                await page.wait_for_load_state("networkidle", timeout=15000)
                
                # Check for 2FA prompt
                await self._handle_2fa_if_present(page)
                
                # After 2FA, check if we're already logged in
                current_url = page.url
                page_content = await page.content()
                
                # If URL changed significantly or we don't see login indicators, we're likely logged in
                login_indicators = ["login", "sign in", "password", "username", "email"]
                if (current_url != url and 
                    not any(indicator in page_content.lower() for indicator in login_indicators)):
                    logging.info("Already authenticated after 2FA - skipping submit button")
                    # Skip the submit button logic since we're already logged in
                else:
                    # Only try submit button if we're still on a login page
                    await self._try_submit_button(page, login_selectors)

            except Exception as e:
                return {
                    "name": f"Login Error: {urlparse(url).netloc}",
                    "content": f"Login failed: {str(e)}",
                    "url": url,
                }

            # Check if login was successful (look for common indicators)
            current_url = page.url
            page_content = await page.content()

            # Simple heuristics for login success
            login_failed_indicators = [
                "login failed",
                "invalid credentials",
                "incorrect password",
                "authentication failed",
                "login error",
                "sign in",
            ]

            if any(
                indicator in page_content.lower()
                for indicator in login_failed_indicators
            ):
                return {
                    "name": f"Login Failed: {urlparse(url).netloc}",
                    "content": "Login appears to have failed based on page content.",
                    "url": url,
                }

            # Save session if requested
            if save_session:
                await self._save_session(page, url)

            # Extract content
            soup = BeautifulSoup(page_content, "html.parser")

            # Remove unwanted elements
            for tag in soup(["nav", "footer", "aside", "script", "style", "header"]):
                tag.decompose()

            if main_content := (
                soup.find("main")
                or soup.find("article")
                or soup.find("div", class_=lambda x: x and "content" in x.lower())
            ):
                text_content = main_content.get_text(separator="\n", strip=True)
            else:
                text_content = soup.get_text(separator="\n", strip=True)

            # Clean up text
            lines = [line.strip() for line in text_content.split("\n") if line.strip()]
            clean_content = "\n".join(lines)

            title = soup.find("title")
            page_title = title.get_text().strip() if title else urlparse(url).netloc

            return {
                "name": f"Authenticated: {page_title}",
                "content": clean_content,
                "url": current_url,
            }

        finally:
            await page.close()

    async def crawl_with_login(
        self,
        base_url: str,
        username: str,
        password: str,
        max_pages: int = 3,
        login_selectors: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, str]]:
        """Crawl multiple pages after authentication."""

        results = []

        # First, authenticate and get the initial page
        initial_result = await self.scrape_with_login(
            base_url, username, password, login_selectors, save_session=True
        )

        if "Error" in initial_result["name"] or "Failed" in initial_result["name"]:
            return [initial_result]

        results.append(initial_result)

        if max_pages <= 1:
            return results

        # Try to find more links to crawl
        page = await self.browser.new_page()

        try:
            # Restore session and navigate
            await self._restore_session(page, base_url)
            await page.goto(base_url, wait_until="networkidle")

            # Find internal links
            links = await page.evaluate(
                """
                () => {
                    const links = Array.from(document.querySelectorAll('a[href]'));
                    return links
                        .map(link => link.href)
                        .filter(href => href.startsWith(window.location.origin))
                        .slice(0, 10); // Limit to first 10 links
                }
            """
            )

            base_domain = urlparse(base_url).netloc
            visited_urls = {base_url}

            for link in links[: max_pages - 1]:
                if link in visited_urls:
                    continue

                visited_urls.add(link)

                try:
                    await page.goto(link, wait_until="networkidle")
                    content = await page.content()

                    soup = BeautifulSoup(content, "html.parser")

                    # Clean content
                    for tag in soup(["nav", "footer", "aside", "script", "style"]):
                        tag.decompose()

                    text_content = soup.get_text(separator="\n", strip=True)
                    lines = [
                        line.strip()
                        for line in text_content.split("\n")
                        if line.strip()
                    ]
                    clean_content = "\n".join(lines)

                    title = soup.find("title")
                    page_title = (
                        title.get_text().strip()
                        if title
                        else f"Page from {base_domain}"
                    )

                    results.append(
                        {
                            "name": f"Authenticated: {page_title}",
                            "content": clean_content,
                            "url": link,
                        }
                    )

                except Exception as e:
                    logging.warning(f"Failed to crawl {link}: {e}")
                    continue

        finally:
            await page.close()

        return results

    async def _save_session(self, page: Page, url: str):
        """Save browser session for reuse."""
        try:
            cookies = await page.context.cookies()
            domain = urlparse(url).netloc

            sessions = {}
            if os.path.exists(self.sessions_file):
                with open(self.sessions_file, "r") as f:
                    sessions = json.load(f)

            sessions[domain] = {"cookies": cookies, "url": url}

            with open(self.sessions_file, "w") as f:
                json.dump(sessions, f, indent=2)

        except Exception as e:
            logging.warning(f"Failed to save session: {e}")

    async def _restore_session(self, page: Page, url: str):
        """Restore saved browser session."""
        try:
            domain = urlparse(url).netloc

            if not os.path.exists(self.sessions_file):
                return

            with open(self.sessions_file, "r") as f:
                sessions = json.load(f)

            if domain in sessions:
                cookies = sessions[domain]["cookies"]
                await page.context.add_cookies(cookies)

        except Exception as e:
            logging.warning(f"Failed to restore session: {e}")

    async def _handle_2fa_if_present(self, page: Page):
        """Handle 2-factor authentication if detected."""
        try:
            # Common 2FA indicators
            twofa_indicators = [
                "verification code", "two-factor", "2fa", "authenticator",
                "security code", "verify", "code", "authentication"
            ]
            
            page_content = await page.content()
            page_text = page_content.lower()
            
            # Check if 2FA is required
            if any(indicator in page_text for indicator in twofa_indicators):
                logging.info("2FA detected, waiting for user intervention...")
                
                # Wait for user to manually handle 2FA (up to 2 minutes)
                for _ in range(24):  # 24 * 5 seconds = 2 minutes
                    await asyncio.sleep(5)
                    current_content = await page.content()
                    
                    # Check if we've moved past 2FA
                    if not any(indicator in current_content.lower() for indicator in twofa_indicators):
                        logging.info("2FA completed successfully")
                        return
                
                logging.warning("2FA timeout - user may need to complete manually")
                
        except Exception as e:
            logging.warning(f"Error handling 2FA: {e}")

    async def _try_submit_button(self, page: Page, login_selectors: Dict[str, str]):
        """Try to click the submit button using various approaches."""
        submit_selector = login_selectors["submit"]
        submit_clicked = False
        
        # First try the detected selector
        try:
            await page.click(submit_selector, timeout=5000)
            submit_clicked = True
        except Exception:
            pass
        
        # If that fails, try common submit button patterns
        if not submit_clicked:
            common_submit_selectors = [
                "input[type='submit']",
                "button[type='submit']",
                "button:has-text('Login')",
                "button:has-text('Sign in')",
                "button:has-text('Log in')",
                "[role='button']:has-text('Login')",
                "[role='button']:has-text('Sign in')"
            ]
            
            for selector in common_submit_selectors:
                try:
                    await page.click(selector, timeout=3000)
                    submit_clicked = True
                    break
                except Exception:
                    continue
        
        # If still no success, try pressing Enter on password field
        if not submit_clicked:
            try:
                await page.press(login_selectors["password"], "Enter")
                submit_clicked = True
            except Exception:
                pass
        
        # Return error if submit failed
        if not submit_clicked:
            return {
                "name": f"Login Error: {urlparse(page.url).netloc}",
                "content": f"Could not find or click submit button. Tried selector: {submit_selector}",
                "url": page.url,
            }
        
        return None  # Success

    async def navigate_and_scrape(
        self, 
        base_url: str, 
        target_urls: list, 
        username: str = None, 
        password: str = None,
        login_selectors: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, str]]:
        """Navigate to multiple URLs after authentication and scrape content."""
        
        if not self.browser:
            raise RuntimeError("Browser not initialized. Use async context manager.")
        
        results = []
        page = await self.browser.new_page()
        
        try:
            # If credentials provided, login first
            if username and password:
                login_result = await self.scrape_with_login(
                    base_url, username, password, login_selectors, save_session=True
                )
                
                if "Error" in login_result["name"] or "Failed" in login_result["name"]:
                    return [login_result]
                
                results.append(login_result)
            else:
                # Just navigate to base URL and restore session
                await self._restore_session(page, base_url)
                await page.goto(base_url, wait_until="networkidle")
            
            # Navigate to each target URL
            for url in target_urls:
                try:
                    logging.info(f"Navigating to: {url}")
                    await page.goto(url, wait_until="networkidle")
                    
                    # Wait a bit for dynamic content
                    await asyncio.sleep(2)
                    
                    content = await page.content()
                    soup = BeautifulSoup(content, "html.parser")
                    
                    # Clean content
                    for tag in soup(["nav", "footer", "aside", "script", "style", "header"]):
                        tag.decompose()
                    
                    # Extract main content
                    if main_content := (
                        soup.find("main")
                        or soup.find("article")
                        or soup.find("div", class_=lambda x: x and "content" in x.lower())
                    ):
                        text_content = main_content.get_text(separator="\n", strip=True)
                    else:
                        text_content = soup.get_text(separator="\n", strip=True)
                    
                    # Clean up text
                    lines = [line.strip() for line in text_content.split("\n") if line.strip()]
                    clean_content = "\n".join(lines)
                    
                    title = soup.find("title")
                    page_title = title.get_text().strip() if title else f"Page from {urlparse(url).netloc}"
                    
                    results.append({
                        "name": f"Navigated: {page_title}",
                        "content": clean_content,
                        "url": url
                    })
                    
                except Exception as e:
                    logging.warning(f"Failed to navigate to {url}: {e}")
                    results.append({
                        "name": f"Navigation Error: {urlparse(url).netloc}",
                        "content": f"Failed to navigate to {url}: {str(e)}",
                        "url": url
                    })
        
        finally:
            await page.close()
        
        return results

# Synchronous wrapper functions for GUI integration
def scrape_with_login_sync(
    url: str,
    username: str,
    password: str,
    login_selectors: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Synchronous wrapper for authenticated scraping."""

    async def _scrape():
        async with AuthenticatedScraper() as scraper:
            return await scraper.scrape_with_login(
                url, username, password, login_selectors
            )

    return asyncio.run(_scrape())


def crawl_with_login_sync(
    url: str,
    username: str,
    password: str,
    max_pages: int = 3,
    login_selectors: Optional[Dict[str, str]] = None,
) -> List[Dict[str, str]]:
    """Synchronous wrapper for authenticated crawling."""

    async def _crawl():
        async with AuthenticatedScraper() as scraper:
            return await scraper.crawl_with_login(
                url, username, password, max_pages, login_selectors
            )

    return asyncio.run(_crawl())


def navigate_and_scrape_sync(
    base_url: str,
    target_urls: list,
    username: str = None,
    password: str = None,
    login_selectors: Optional[Dict[str, str]] = None,
) -> List[Dict[str, str]]:
    """Synchronous wrapper for navigation and scraping."""

    async def _navigate():
        async with AuthenticatedScraper() as scraper:
            return await scraper.navigate_and_scrape(
                base_url, target_urls, username, password, login_selectors
            )

    return asyncio.run(_navigate())


def analyze_login_form_sync(url: str) -> Dict[str, str]:
    """Analyze a page to detect login form elements."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        scraper = AuthenticatedScraper()
        return scraper.analyze_login_form(response.text)

    except Exception as e:
        return {"error": f"Failed to analyze page: {str(e)}"}
