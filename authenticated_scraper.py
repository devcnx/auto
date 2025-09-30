"""Authenticated web scraping with AI-assisted element detection."""

import asyncio
import contextlib
import json
import logging
import os
import inspect
import random
from typing import Dict, Optional, List, Any, Callable, Awaitable
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
        self.playwright_cm = None
        self.playwright = None
        self.remote_endpoint = os.getenv("PLAYWRIGHT_REMOTE_ENDPOINT")

    async def __aenter__(self):
        """Async context manager entry."""
        self.playwright_cm = async_playwright()
        self.playwright = await self.playwright_cm.__aenter__()
        if self.remote_endpoint:
            try:
                self.browser = await self.playwright.chromium.connect_over_cdp(self.remote_endpoint)
            except Exception as exc:
                logging.error("Failed to connect to remote browser at %s: %s", self.remote_endpoint, exc)
                raise
        else:
            self.browser = await self.playwright.chromium.launch(headless=False)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.browser and not self.remote_endpoint:
            await self.browser.close()
        if self.playwright_cm:
            await self.playwright_cm.__aexit__(exc_type, exc_val, exc_tb)

    def set_remote_endpoint(self, endpoint: Optional[str]):
        """Update the remote debugging endpoint."""
        self.remote_endpoint = endpoint

    @staticmethod
    def apply_remote_endpoint(endpoint: Optional[str]):
        if endpoint:
            os.environ["PLAYWRIGHT_REMOTE_ENDPOINT"] = endpoint
        else:
            os.environ.pop("PLAYWRIGHT_REMOTE_ENDPOINT", None)

    async def _generate_page_analysis(
        self,
        url: str,
        clean_content: str,
        include_followups: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Use the LLM to summarize page content and suggest follow-ups."""

        if not clean_content.strip():
            return None

        truncated = clean_content[:4000]
        system_prompt = (
            "You are an analytical research assistant helping a user understand web pages. "
            "Provide clear, structured insights suitable for decision-making."
        )

        followup_instructions = (
            "\n3. Provide up to three follow-up research questions that would help gather "
            "more context or confirm details."
            if include_followups
            else ""
        )

        user_msg = (
            f"URL: {url}\n\n"
            "Analyze the following page content. Respond in Markdown with the sections:\n"
            "1. Summary (bullet list with at most 3 bullets).\n"
            "2. Key Data Points (list important numbers, addresses, names, etc.)."
            f"{followup_instructions}\n\n"
            "CONTENT:\n"
            f"{truncated}"
        )

        def _run_model() -> Optional[str]:
            try:
                chunks: List[str] = []
                for chunk in query_ollama_chat_for_gui(
                    model=DEFAULT_MODEL,
                    system_prompt=system_prompt,
                    user_msg=user_msg,
                ):
                    chunks.append(chunk)
                return "".join(chunks).strip()
            except Exception as exc:  # noqa: BLE001
                logging.warning("Failed to generate page analysis for %s: %s", url, exc)
                return None

        analysis_text = await asyncio.to_thread(_run_model)
        if not analysis_text:
            return None

        followups: List[str] = []
        if include_followups:
            for line in analysis_text.splitlines():
                stripped = line.strip()
                if stripped.startswith("-"):
                    followups.append(stripped.lstrip("-•* "))
            followups = followups[:3]

        return {"analysis": analysis_text, "followups": followups}

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
            try:
                response = "".join(
                    query_ollama_chat_for_gui(
                        model=DEFAULT_MODEL,
                        system_prompt="You are a web scraping expert. Analyze HTML and return only valid JSON with CSS selectors.",
                        user_msg=prompt,
                        conversation_history=[],
                    )
                )
            except Exception as e:
                logging.error(f"Failed to query Ollama API: {e}")
                return {"error": f"AI service unavailable: {str(e)}"}
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

    async def detect_captcha_or_verification(self, page: Page) -> Dict[str, str]:
        """Detect if page contains CAPTCHA or human verification challenges."""
        try:
            # Common CAPTCHA and verification indicators
            captcha_selectors = [
                # reCAPTCHA
                'iframe[src*="recaptcha"]',
                ".g-recaptcha",
                "#recaptcha",
                "[data-sitekey]",
                # hCaptcha
                'iframe[src*="hcaptcha"]',
                ".h-captcha",
                # Cloudflare
                ".cf-challenge-running",
                ".cf-browser-verification",
                "#challenge-form",
                # Generic verification
                '[class*="captcha"]',
                '[id*="captcha"]',
                '[class*="verification"]',
                '[id*="verification"]',
                '[class*="challenge"]',
                '[id*="challenge"]',
            ]

            verification_found = []

            for selector in captcha_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    if elements:
                        verification_found.append(selector)
                except Exception:
                    continue

            # Check page content for verification text
            page_content = await page.content()
            verification_phrases = [
                "i'm not a robot",
                "verify you are human",
                "complete the security check",
                "prove you're not a robot",
                "captcha",
                "recaptcha",
                "hcaptcha",
                "cloudflare",
                "security challenge",
                "bot detection",
                "please verify",
                "human verification",
                "press & hold",
            ]

            content_matches = [
                phrase
                for phrase in verification_phrases
                if phrase.lower() in page_content.lower()
            ]

            if verification_found or content_matches:
                return {
                    "verification_detected": True,
                    "selectors_found": verification_found,
                    "content_matches": content_matches,
                    "page_title": await page.title(),
                    "current_url": page.url,
                }

            return {"verification_detected": False}

        except Exception as e:
            logging.error(f"Error detecting verification: {e}")
            return {"verification_detected": False, "error": str(e)}

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

            # Check for CAPTCHA or human verification challenges
            verification_check = await self.detect_captcha_or_verification(page)
            if verification_check.get("verification_detected"):
                handled = await self._handle_press_and_hold_challenge(page)
                if not handled:
                    return {
                        "name": f"Verification Required: {urlparse(url).netloc}",
                        "content": f"Human verification detected on {url}. Manual intervention required.",
                        "url": url,
                        "verification_info": verification_check,
                        "requires_manual_verification": True,
                    }
            else:
                await self._handle_press_and_hold_challenge(page)

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
                    "#user",
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
                    "#passwd",
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
                if current_url != url and not any(
                    indicator in page_content.lower() for indicator in login_indicators
                ):
                    logging.info(
                        "Already authenticated after 2FA - skipping submit button"
                    )
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
                "verification code",
                "two-factor",
                "2fa",
                "authenticator",
                "security code",
                "verify",
                "code",
                "authentication",
            ]

            page_content = await page.content()
            page_text = page_content.lower()

            # Check if 2FA is required
            if any(indicator in page_text for indicator in twofa_indicators):
                logging.info("2FA detected, waiting for user intervention...")

                # Wait for user to manually handle 2FA (up to 5 minutes)
                for i in range(60):  # 60 * 5 seconds = 5 minutes
                    await asyncio.sleep(5)
                    current_content = await page.content()

                    # Check if we've moved past 2FA
                    if not any(
                        indicator in current_content.lower()
                        for indicator in twofa_indicators
                    ):
                        logging.info("2FA completed successfully")
                        return

                    # Log progress every 30 seconds
                    if i % 6 == 0:
                        logging.info(
                            f"Still waiting for 2FA completion... ({(i+1)*5} seconds elapsed)"
                        )

                logging.warning(
                    "2FA timeout after 5 minutes - user may need to complete manually"
                )

        except Exception as e:
            logging.warning(f"Error handling 2FA: {e}")

    async def _handle_press_and_hold_challenge(self, page: Page) -> bool:
        """Handle Zillow-style press-and-hold bot verification challenges."""
        try:
            button = page.locator("text='Press & Hold'")
            if await button.count() == 0:
                return False

            # Wait for the button to be visible
            await button.first.wait_for(state="visible", timeout=5000)
            bbox = await button.first.bounding_box()
            if not bbox:
                return False

            x = bbox["x"] + bbox["width"] / 2
            y = bbox["y"] + bbox["height"] / 2

            await page.mouse.move(x, y)
            await page.mouse.down()
            await asyncio.sleep(3)
            await page.mouse.up()
            await page.wait_for_timeout(1000)

            try:
                await button.first.wait_for(state="hidden", timeout=8000)
            except Exception:
                logging.warning("Press & Hold challenge may still be visible.")
                return False

            logging.info("Press & Hold bot challenge solved automatically.")
            return True
        except Exception as exc:
            logging.warning("Failed to handle Press & Hold challenge: %s", exc)
            return False

    async def _simulate_human_interaction(self, page: Page):
        """Introduce randomness to mimic human behavior."""
        try:
            viewport = page.viewport_size or {"width": 1280, "height": 720}
            base_x = random.uniform(50, viewport["width"] - 50)
            base_y = random.uniform(100, viewport["height"] - 50)
            await page.mouse.move(base_x, base_y, steps=random.randint(5, 15))

            # Occasionally move to a secondary point to mimic curiosity
            if random.random() < 0.4:
                alt_x = min(viewport["width"] - 10, max(10, base_x + random.uniform(-120, 120)))
                alt_y = min(viewport["height"] - 10, max(10, base_y + random.uniform(-150, 150)))
                await page.mouse.move(alt_x, alt_y, steps=random.randint(4, 10))

            # Random scroll bursts
            for _ in range(random.randint(1, 3)):
                scroll_distance = random.randint(150, 600)
                await page.mouse.wheel(0, scroll_distance)
                await asyncio.sleep(random.uniform(0.3, 1.1))

            # Chance to scroll back up slightly
            if random.random() < 0.3:
                await page.mouse.wheel(0, -random.randint(80, 200))
                await asyncio.sleep(random.uniform(0.2, 0.8))

            # Micro idle time to simulate reading
            await asyncio.sleep(random.uniform(1.0, 3.0))
        except Exception as exc:
            logging.debug("Human interaction simulation failed: %s", exc)

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
                "[role='button']:has-text('Sign in')",
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
        login_selectors: Optional[Dict[str, str]] = None,
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
                    for tag in soup(
                        ["nav", "footer", "aside", "script", "style", "header"]
                    ):
                        tag.decompose()

                    # Extract main content
                    if main_content := (
                        soup.find("main")
                        or soup.find("article")
                        or soup.find(
                            "div", class_=lambda x: x and "content" in x.lower()
                        )
                    ):
                        text_content = main_content.get_text(separator="\n", strip=True)
                    else:
                        text_content = soup.get_text(separator="\n", strip=True)

                    # Clean up text
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
                        else f"Page from {urlparse(url).netloc}"
                    )

                    results.append(
                        {
                            "name": f"Navigated: {page_title}",
                            "content": clean_content,
                            "url": url,
                        }
                    )

                except Exception as e:
                    logging.warning(f"Failed to navigate to {url}: {e}")
                    results.append(
                        {
                            "name": f"Navigation Error: {urlparse(url).netloc}",
                            "content": f"Failed to navigate to {url}: {str(e)}",
                            "url": url,
                        }
                    )

        finally:
            await page.close()

        return results


# Synchronous wrapper functions for GUI integration
async def playwright_crawl(
    start_url: str,
    max_pages: int = 10,
    same_domain_only: bool = True,
    username: Optional[str] = None,
    password: Optional[str] = None,
    login_selectors: Optional[Dict[str, str]] = None,
    include_ai_summary: bool = False,
    progress_callback: Optional[
        Callable[[Dict[str, Any]], Awaitable[bool] | bool]
    ] = None,
) -> List[Dict[str, str]]:
    """Generic Playwright-based crawler that works with or without authentication."""

    async with AuthenticatedScraper() as scraper:
        results: List[Dict[str, str]] = []

        if username and password:
            initial = await scraper.scrape_with_login(
                start_url, username, password, login_selectors, save_session=True
            )
            results.append(initial)

            if "Error" in initial.get("name", "") or "Failed" in initial.get("name", ""):
                return results

        if not scraper.browser:
            return results

        try:
            visited: set[str] = set()
            queue: List[str] = [start_url]
            parsed_count = 0

            while queue and parsed_count < max_pages:
                url = queue.pop(0)
                if url in visited:
                    continue
                visited.add(url)

                success = False
                last_exception: Optional[Exception] = None
                page = None

                for attempt in range(3):
                    attempt_page = await scraper.browser.new_page()
                    attempt_page.set_default_navigation_timeout(45000)

                    try:
                        await scraper._restore_session(attempt_page, url)
                        await attempt_page.goto(url, wait_until="domcontentloaded")
                        await attempt_page.wait_for_timeout(random.randint(1500, 3500))
                        await scraper._simulate_human_interaction(attempt_page)

                        try:
                            await attempt_page.wait_for_load_state("networkidle", timeout=20000)
                        except Exception:
                            await attempt_page.wait_for_selector("body", timeout=8000)

                        await scraper._handle_press_and_hold_challenge(attempt_page)

                        success = True
                        page = attempt_page
                        break
                    except Exception as exc:
                        logging.warning(
                            "Attempt %d failed to load %s: %s",
                            attempt + 1,
                            url,
{{ ... }}
                        )
                        last_exception = exc
                    finally:
                        if not success:
                            await attempt_page.close()

                if not success or page is None:
                    results.append(
                        {
                            "name": f"Navigation Timeout: {urlparse(url).netloc}",
                            "content": f"Failed to load {url} after multiple attempts. Last error: {last_exception}",
                            "url": url,
                        }
                    )
                    continue

                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")

                for tag in soup(["nav", "footer", "aside", "script", "style", "header"]):
                    tag.decompose()

                text_content = soup.get_text(separator="\n", strip=True)
                clean_lines = [line.strip() for line in text_content.split("\n") if line.strip()]
                clean_content = "\n".join(clean_lines)

                title = soup.find("title")
                analysis_info = None
                if include_ai_summary:
                    analysis_info = await scraper._generate_page_analysis(
                        url, clean_content, include_followups=True
                    )

                result_entry: Dict[str, Any] = {
                    "name": f"Crawled: {title.get_text().strip() if title else urlparse(url).netloc}",
                    "content": clean_content,
                    "url": url,
                }

                if analysis_info:
                    result_entry["analysis"] = analysis_info.get("analysis")
                    result_entry["followups"] = analysis_info.get("followups", [])

                link_hrefs = await page.evaluate(
                    """
                    () => Array.from(document.querySelectorAll('a[href]'))
                        .map(a => a.href)
                        .filter(Boolean)
                    """
                )

                candidate_links: List[str] = []

                base_domain = urlparse(start_url).netloc

                for href in link_hrefs:
                    parsed = urlparse(href)
                    if parsed.scheme not in {"http", "https"}:
                        continue
                    if same_domain_only and parsed.netloc != base_domain:
                        continue
                    if href in visited or href in queue:
                        continue
                    candidate_links.append(href)
                    queue.append(href)

                result_entry["candidate_links"] = candidate_links[:10]

                results.append(result_entry)
                parsed_count += 1

                if progress_callback:
                    callback_result = progress_callback(result_entry)
                    if inspect.isawaitable(callback_result):
                        callback_result = await callback_result
                    if callback_result is False:
                        await page.close()
                        break

                if parsed_count >= max_pages:
                    break
                await page.close()
        finally:
            with contextlib.suppress(Exception):
                if page is not None:
                    await page.close()

        return results


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


def playwright_crawl_sync(
    start_url: str,
    max_pages: int = 10,
    same_domain_only: bool = True,
    username: Optional[str] = None,
    password: Optional[str] = None,
    login_selectors: Optional[Dict[str, str]] = None,
    include_ai_summary: bool = False,
    progress_callback: Optional[
        Callable[[Dict[str, Any]], Awaitable[bool] | bool]
    ] = None,
) -> List[Dict[str, str]]:
    """Synchronous wrapper for the generic Playwright crawler."""

    async def _crawl():
        return await playwright_crawl(
            start_url,
            max_pages=max_pages,
            same_domain_only=same_domain_only,
            username=username,
            password=password,
            login_selectors=login_selectors,
            include_ai_summary=include_ai_summary,
            progress_callback=progress_callback,
        )

    return asyncio.run(_crawl())


def analyze_login_form_sync(url: str) -> Dict[str, str]:
    """Analyze a page to detect login form elements."""
    try:
        # Add headers to appear more like a real browser
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        scraper = AuthenticatedScraper()
        return scraper.analyze_login_form(response.text)

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            return {
                "error": "Site blocks automated access (403 Forbidden)",
                "suggestion": "This site prevents automated analysis. Try using Playwright-based analysis or manual selector entry.",
                "manual_mode": True,
                "common_selectors": {
                    "username": "input[type='email'], input[name='username'], input[name='email'], #username, #email",
                    "password": "input[type='password'], input[name='password'], #password",
                    "submit": "button[type='submit'], input[type='submit'], button:contains('Sign in'), button:contains('Login')",
                },
            }
        else:
            return {"error": f"HTTP {e.response.status_code}: {str(e)}"}
    except requests.exceptions.RequestException as e:
        return {"error": f"Network error: {str(e)}"}
    except Exception as e:
        return {"error": f"Failed to analyze page: {str(e)}"}
