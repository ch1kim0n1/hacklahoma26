"""
Browser automation agent using browser-use library.
Enables AI-controlled browser navigation, form filling, and web interactions.

Uses the official browser-use API: https://github.com/browser-use/browser-use
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional, Callable

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class BrowserAgent:
    """AI-powered browser automation agent using browser-use.

    Uses ChatBrowserUse (browser-use's optimized LLM) by default, or can use OpenAI.
    """

    def __init__(
        self,
        use_cloud: bool = False,
        headless: bool = False,
        on_status_update: Optional[Callable[[str], None]] = None,
        use_openai_fallback: bool = False,
    ):
        """Initialize the browser agent.

        Args:
            use_cloud: Whether to use Browser Use Cloud (stealth browser).
            headless: Whether to run browser in headless mode (ignored if use_cloud=True).
            on_status_update: Optional callback for status updates.
            use_openai_fallback: If True, use OpenAI instead of ChatBrowserUse.
        """
        # Check for required API keys
        self.browser_use_api_key = os.getenv("BROWSER_USE_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")

        self.use_cloud = use_cloud
        self.headless = headless
        self.on_status_update = on_status_update
        self.use_openai_fallback = use_openai_fallback

        self._browser = None
        self._llm = None
        self._initialized = False

        logger.info("BrowserAgent created (use_cloud=%s, headless=%s)", use_cloud, headless)

    def _emit_status(self, message: str) -> None:
        """Emit a status update."""
        logger.info("BrowserAgent: %s", message)
        if self.on_status_update:
            self.on_status_update(message)

    async def _ensure_initialized(self) -> None:
        """Lazily initialize browser-use components."""
        if self._initialized:
            return

        self._emit_status("Initializing browser automation...")

        try:
            from browser_use import Agent, Browser, ChatBrowserUse

            # Initialize LLM - prefer ChatBrowserUse, fallback to OpenAI
            if not self.use_openai_fallback and self.browser_use_api_key:
                self._llm = ChatBrowserUse()
                logger.info("Using ChatBrowserUse LLM")
            elif self.openai_api_key:
                # Fallback to OpenAI if no browser-use API key
                try:
                    from langchain_openai import ChatOpenAI
                    self._llm = ChatOpenAI(
                        model="gpt-4o",
                        api_key=self.openai_api_key,
                        temperature=0.0,
                    )
                    logger.info("Using OpenAI LLM fallback")
                except ImportError:
                    raise ImportError(
                        "langchain-openai not installed. Run: pip install langchain-openai"
                    )
            else:
                raise ValueError(
                    "No API key found. Set BROWSER_USE_API_KEY or OPENAI_API_KEY in .env file."
                )

            # Configure browser
            self._browser = Browser(
                use_cloud=self.use_cloud,
                headless=self.headless if not self.use_cloud else None,
            )

            self._initialized = True
            self._emit_status("Browser automation ready")
            logger.info("BrowserAgent initialized successfully")

        except ImportError as e:
            logger.error("Failed to import browser-use dependencies: %s", e)
            raise ImportError(
                "browser-use not installed. Run:\n"
                "  pip install browser-use\n"
                "  uvx browser-use install"
            ) from e
        except Exception as e:
            logger.error("Failed to initialize BrowserAgent: %s", e)
            raise

    async def run_task(self, task: str, max_steps: int = 25) -> dict[str, Any]:
        """Execute a browser automation task.

        Args:
            task: Natural language description of what to do in the browser.
            max_steps: Maximum number of steps the agent can take.

        Returns:
            Dictionary with task result including success status and message.
        """
        await self._ensure_initialized()

        self._emit_status(f"Starting browser task: {task[:50]}...")

        try:
            from browser_use import Agent

            # Create agent for this task
            agent = Agent(
                task=task,
                llm=self._llm,
                browser=self._browser,
            )

            # Run the task
            history = await agent.run(max_steps=max_steps)

            self._emit_status("Browser task completed")

            # Extract result from history
            result_text = "Task executed successfully"
            if history:
                # Get the final result from agent history
                result_text = str(history)

            return {
                "success": True,
                "message": f"Task completed: {task}",
                "result": result_text,
            }

        except Exception as e:
            error_msg = f"Browser task failed: {str(e)}"
            logger.error(error_msg)
            self._emit_status(error_msg)
            return {
                "success": False,
                "message": error_msg,
                "error": str(e),
            }

    async def navigate_to(self, url: str) -> dict[str, Any]:
        """Navigate browser to a specific URL.

        Args:
            url: The URL to navigate to.

        Returns:
            Result dictionary.
        """
        return await self.run_task(f"Navigate to {url}")

    async def fill_form(
        self,
        form_description: str,
        field_values: dict[str, str],
    ) -> dict[str, Any]:
        """Fill out a form on the current page.

        Args:
            form_description: Description of the form (e.g., "login form", "signup form").
            field_values: Dictionary mapping field names to values.

        Returns:
            Result dictionary.
        """
        fields_str = ", ".join(f"{k}='{v}'" for k, v in field_values.items())
        task = f"Fill out the {form_description} with these values: {fields_str}"
        return await self.run_task(task)

    async def click_element(self, element_description: str) -> dict[str, Any]:
        """Click on an element described in natural language.

        Args:
            element_description: Description of element to click (e.g., "submit button", "login link").

        Returns:
            Result dictionary.
        """
        return await self.run_task(f"Click on the {element_description}")

    async def extract_content(self, content_description: str) -> dict[str, Any]:
        """Extract content from the current page.

        Args:
            content_description: What content to extract.

        Returns:
            Result dictionary with extracted content.
        """
        return await self.run_task(f"Extract the {content_description} from this page")

    async def search_and_navigate(self, query: str, site: Optional[str] = None) -> dict[str, Any]:
        """Search for something and navigate to a result.

        Args:
            query: Search query.
            site: Optional specific site to search on (e.g., "google", "bing").

        Returns:
            Result dictionary.
        """
        if site:
            task = f"Go to {site} and search for '{query}'"
        else:
            task = f"Search the web for '{query}' and go to the most relevant result"
        return await self.run_task(task)

    async def complete_checkout(
        self,
        payment_info: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """Complete a checkout process on an e-commerce site.

        Args:
            payment_info: Optional payment information (use carefully).

        Returns:
            Result dictionary.
        """
        task = "Complete the checkout process"
        if payment_info:
            # Only include non-sensitive info in the task
            task += " by filling in the required fields"
        return await self.run_task(task)

    async def login(
        self,
        site_url: str,
        username: str,
        password: str,
    ) -> dict[str, Any]:
        """Log into a website.

        Args:
            site_url: URL of the login page.
            username: Username or email.
            password: Password.

        Returns:
            Result dictionary.
        """
        task = f"Go to {site_url}, find the login form, enter username '{username}' and password, then click the login button"
        # Note: password is passed to the LLM, so use with caution
        return await self.run_task(
            f"Go to {site_url}, find the login form, enter '{username}' in the username/email field, "
            f"enter '{password}' in the password field, then click the login/sign in button"
        )

    async def interact_with_page(self, instruction: str) -> dict[str, Any]:
        """General page interaction with natural language instruction.

        Args:
            instruction: What to do on the current page.

        Returns:
            Result dictionary.
        """
        return await self.run_task(instruction)

    async def close(self) -> None:
        """Close the browser and cleanup resources."""
        if self._browser:
            try:
                # browser-use Browser may not have a close method on BrowserSession
                # Try different close patterns
                if hasattr(self._browser, 'close'):
                    await self._browser.close()
                elif hasattr(self._browser, 'session') and hasattr(self._browser.session, 'close'):
                    await self._browser.session.close()
                self._emit_status("Browser closed")
            except Exception as e:
                logger.warning("Error closing browser: %s", e)
            finally:
                self._browser = None
                self._initialized = False

    def run_sync(self, task: str, max_steps: int = 25) -> dict[str, Any]:
        """Synchronous wrapper for run_task.

        Args:
            task: Natural language task description.
            max_steps: Maximum steps.

        Returns:
            Result dictionary.
        """
        return asyncio.run(self.run_task(task, max_steps))


# Global instance
_browser_agent: Optional[BrowserAgent] = None


def get_browser_agent(
    use_cloud: bool = False,
    headless: bool = False,
    on_status_update: Optional[Callable[[str], None]] = None,
) -> BrowserAgent:
    """Get or create the global browser agent instance.

    Args:
        use_cloud: Whether to use Browser Use Cloud (stealth browser).
        headless: Whether to run in headless mode.
        on_status_update: Optional status callback.

    Returns:
        BrowserAgent instance.
    """
    global _browser_agent
    if _browser_agent is None:
        _browser_agent = BrowserAgent(
            use_cloud=use_cloud,
            headless=headless,
            on_status_update=on_status_update,
        )
    return _browser_agent


async def close_browser_agent() -> None:
    """Close the global browser agent if it exists."""
    global _browser_agent
    if _browser_agent:
        await _browser_agent.close()
        _browser_agent = None
