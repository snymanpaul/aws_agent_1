"""
Level 73: AgentCore Browser — A Managed Headless Chrome an Agent Can Drive
=========================================================================
AWS Bedrock AgentCore — `bedrock_agentcore.tools.browser_client`.

Goal: give an agent a real web browser without running one on your machine.
AgentCore's Browser is a managed, isolated headless Chrome you reach over the
Chrome DevTools Protocol (CDP): open a `browser_session(...)`, get a signed
websocket endpoint, connect Playwright to it, and drive the page. It is the
sibling of L72's Code Interpreter — same "managed tool for an agent" pattern, but
for the web instead of a REPL.

The connection shape (this is the whole trick):
    browser_session(region)        -> a managed Chrome, started for you
    client.generate_ws_headers()   -> (wss:// CDP url, SigV4-signed headers)
    async_playwright.connect_over_cdp(ws_url, headers=...)  -> drive the REMOTE browser
    # No local browser binaries: Playwright is just a CDP client to the AWS browser.

Why ASYNC Playwright (a hard-won lesson):
    Strands runs the agent loop on its own asyncio event loop. The SYNC Playwright
    API runs its own loop in a greenlet, and the two collide the moment a Strands
    tool touches a sync Playwright object ("greenlet.error: cannot switch to a
    different thread" + TargetClosedError). Using the ASYNC Playwright API with
    agent.invoke_async keeps everything on ONE event loop — no thread crossing.

Depends on: L72 (Code Interpreter — the sibling managed tool), L27 (AgentCore plane)
Unlocks:    safe agentic web browsing/scraping; human-on-the-loop via take_control.

Iterations:
  1. Connect + navigate + extract   — connect over CDP, load a page, read title/text.
  2. Interact with a page           — fill a field and read it back (self-contained).
  3. Wire it to a Strands agent      — an agent answers a question by BROWSING.

Critical API facts (validated by live probe, not docs):
    * from bedrock_agentcore.tools.browser_client import browser_session
      with browser_session("us-east-1") as client:   # starts managed Chrome, stops on exit
          ws_url, headers = client.generate_ws_headers()
    * generate_ws_headers() -> (str ws_url, dict headers). Headers are SigV4-signed
      (Host, X-Amz-Date, Authorization, Upgrade) — pass them to connect_over_cdp.
    * Use the ASYNC Playwright API + agent.invoke_async (see note above). Reuse the
      managed Chrome's existing context/page: browser.contexts[0].pages[0].
    * generate_live_view_url(expires=300) -> a URL a human can watch the session at.
      take_control() / release_control() hand the browser between agent and human.
    * The context manager stops the managed browser on exit (auto-teardown); sessions
      also time out. Uses the AWS-managed default browser — no custom resource to delete.

Usage:
    AWS_PROFILE=<admin-profile> uv run python 16_agentcore_tools/browser.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3
from bedrock_agentcore.tools.browser_client import browser_session
from playwright.async_api import async_playwright

from strands import Agent, tool

from tools import get_model  # importing this loads LESSON_DOTENV (for the Gemini key)

# GOTCHA (see L72): LESSON_DOTENV may inject static AWS_* keys that override the SSO
# profile -> InvalidClientTokenId. When AWS_PROFILE is set, drop them so the profile wins.
if os.environ.get("AWS_PROFILE"):
    for _k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        os.environ.pop(_k, None)

REGION = "us-east-1"


def preflight() -> bool:
    try:
        ident = boto3.client("sts", region_name=REGION).get_caller_identity()
        print(f"  authenticated as {ident['Arn'].split('/')[-1]} (acct {ident['Account']})")
        return True
    except Exception as e:
        print(f"  AWS credentials unavailable: {str(e)[:90]}")
        print("  -> run:  aws sso login --profile <your-admin-profile>")
        return False


async def current_page(browser):
    """Reuse the managed Chrome's existing context/page instead of opening new ones."""
    ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
    return ctx.pages[0] if ctx.pages else await ctx.new_page()


# ---------------------------------------------------------------------------
# ITERATION 1: connect + navigate + extract
# ---------------------------------------------------------------------------
async def iteration_1_navigate(client, page) -> None:
    print("\n" + "=" * 70)
    print("ITERATION 1: connect over CDP, navigate, extract")
    print("=" * 70)
    await page.goto("https://example.com", wait_until="domcontentloaded", timeout=30000)
    title = await page.title()
    h1 = await page.locator("h1").inner_text()
    print(f"  navigated example.com -> title={title!r} h1={h1!r}")
    live = client.generate_live_view_url(expires=300)  # a human can watch THIS session
    print(f"  live-view URL (a human can watch): {live.split('?')[0][:54]}...")
    assert title == "Example Domain" and h1 == "Example Domain"
    print("  OK: a managed, remote Chrome rendered the page; we read the DOM over CDP.")


# ---------------------------------------------------------------------------
# ITERATION 2: interact with a page
# ---------------------------------------------------------------------------
async def iteration_2_interact(page) -> None:
    print("\n" + "=" * 70)
    print("ITERATION 2: interact — fill a field and read it back")
    print("=" * 70)
    # Self-contained page (no external dependency) so the demo is deterministic.
    await page.set_content(
        '<form><input id="q" name="q" value=""/>'
        '<button id="go" type="button" onclick="document.title=document.getElementById(\'q\').value">go</button>'
        '</form>'
    )
    await page.fill("#q", "agentcore browser")
    await page.click("#go")
    value = await page.input_value("#q")
    new_title = await page.title()
    print(f"  typed into #q -> input_value={value!r}; clicked go -> document.title={new_title!r}")
    assert value == "agentcore browser" and new_title == "agentcore browser"
    print("  OK: real input + click + JS execution — full page interaction, not just reads.")


# ---------------------------------------------------------------------------
# ITERATION 3: wire the browser to a Strands agent (async, one event loop)
# ---------------------------------------------------------------------------
async def iteration_3_agent(page) -> None:
    print("\n" + "=" * 70)
    print("ITERATION 3: give a Strands agent a browse tool (async)")
    print("=" * 70)

    @tool
    async def fetch_page_text(url: str) -> str:
        """Navigate the browser to a URL and return the page's visible text."""
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return (await page.inner_text("body"))[:1500]

    agent = Agent(
        model=get_model("gemini-2.5-flash"),
        tools=[fetch_page_text],
        system_prompt="Answer questions about web pages by calling fetch_page_text on the URL. "
                      "Quote what you find.",
        callback_handler=None,
    )
    result = await agent.invoke_async("What is the main heading on https://example.com ?")
    answer = str(result)
    print(f"  agent answer: {answer.strip()[:80]!r}")
    assert "Example Domain" in answer, "the agent should report the page's heading from a live fetch"
    print("  OK: the agent answered by driving the managed browser itself.")


def summary() -> None:
    print("\n" + "=" * 70)
    print("L73 COMPLETE — Key Takeaways")
    print("=" * 70)
    print("""
1. Connect to a REMOTE browser over CDP
   with browser_session("us-east-1") as client:
       ws_url, headers = client.generate_ws_headers()   # SigV4-signed
       browser = await playwright.chromium.connect_over_cdp(ws_url, headers=headers)
   Playwright is only a CDP client — the Chrome runs in AWS, not on your machine.

2. Use the ASYNC API with invoke_async
   Strands and sync-Playwright each run their own event loop and collide. Async
   Playwright + agent.invoke_async keeps it all on one loop.

3. Full interaction, not just scraping
   goto / inner_text / fill / click / JS all work — it's a real browser.

4. Human-on-the-loop built in
   generate_live_view_url() lets a human watch; take_control()/release_control()
   hand the browser between agent and human mid-session.

5. The pattern: a managed tool for an agent
   Back an agent's browse tool with the session and it navigates the web WITHOUT
   a browser on your box. Sibling of L72 (Code Interpreter): same managed-tool
   shape, web instead of a REPL.
""")


async def main() -> None:
    print("AgentCore Browser — L73")
    if not preflight():
        sys.exit(1)
    with browser_session(REGION) as client:
        print(f"  browser session: {client.session_id}")
        ws_url, headers = client.generate_ws_headers()
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(ws_url, headers=headers)
            page = await current_page(browser)
            try:
                await iteration_1_navigate(client, page)
                await iteration_2_interact(page)
                await iteration_3_agent(page)
            finally:
                await browser.close()
    print("\n  (browser_session context exited -> managed Chrome stopped)")
    summary()


if __name__ == "__main__":
    asyncio.run(main())
