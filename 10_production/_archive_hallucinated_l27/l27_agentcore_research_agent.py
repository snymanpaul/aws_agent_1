"""
Level 27: Research Agent for AWS Bedrock AgentCore
===================================================

Adapts L26 Research Agent for AWS deployment with:
- Bedrock models (Claude Sonnet/Haiku) instead of LiteLLM
- DynamoDB for session memory and checkpoints
- Configurable external endpoints for Perplexity and Graphiti
- FastAPI wrapper for AgentCore compatibility

Endpoints:
- POST /invocations - Execute research query
- GET /ping - Health check

Run locally: uv run python 10_production/l27_agentcore_research_agent.py
Docker: See Dockerfile in this directory
"""

import os
import sys
import json
import hashlib
import time
import re
import uuid
import requests
from datetime import datetime
from typing import Optional, Literal, Any
from enum import Enum
from pydantic import BaseModel, Field
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import our L27 modules
from bedrock_models import (
    get_model_for_environment,
    get_perplexity_config,
    get_graphiti_config,
    is_aws_environment,
)
from dynamodb_persistence import (
    DynamoDBPersistence,
    LocalPersistence,
    get_persistence,
)

# Strands imports
from strands import Agent, tool

# =============================================================================
# Data Models (from L26)
# =============================================================================


class ResearchScope(str, Enum):
    """Depth of research investigation."""
    NARROW = "narrow"
    MEDIUM = "medium"
    COMPREHENSIVE = "comprehensive"


class SourceType(str, Enum):
    """Types of research sources."""
    WEB = "web"
    ACADEMIC = "academic"
    DOCUMENT = "document"
    EXPERT = "expert"


class ResearchStepType(str, Enum):
    """Types of steps in a research plan."""
    SEARCH = "search"
    RETRIEVE = "retrieve"
    ANALYZE = "analyze"
    SYNTHESIZE = "synthesize"
    VALIDATE = "validate"


class ResearchQuery(BaseModel):
    """A research question to investigate."""
    query_id: str = Field(default_factory=lambda: hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8])
    question: str = Field(..., description="The research question")
    scope: ResearchScope = Field(default=ResearchScope.MEDIUM)
    max_sources: int = Field(default=10, ge=1, le=50)
    created_at: datetime = Field(default_factory=datetime.now)


class SearchResult(BaseModel):
    """A single search result."""
    title: str
    url: str
    snippet: str
    source_type: SourceType = SourceType.WEB
    credibility_hint: Optional[str] = None


class ResearchSource(BaseModel):
    """A source used in research."""
    source_id: str = Field(default_factory=lambda: hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8])
    title: str
    url: Optional[str] = None
    source_type: SourceType = SourceType.WEB
    credibility_score: float = Field(default=0.7, ge=0.0, le=1.0)
    content_summary: str = ""
    raw_content: Optional[str] = None


class ResearchFinding(BaseModel):
    """A fact or insight extracted from sources."""
    finding_id: str = Field(default_factory=lambda: hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8])
    claim: str
    supporting_sources: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    category: str = "general"


class ResearchReport(BaseModel):
    """Final research output."""
    report_id: str = Field(default_factory=lambda: hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8])
    query: ResearchQuery
    executive_summary: str = ""
    key_findings: list[ResearchFinding] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)
    methodology: str = ""
    limitations: list[str] = Field(default_factory=list)
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    citations: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    iteration_count: int = 1

    def to_markdown(self) -> str:
        """Convert report to markdown format."""
        md = f"# Research Report: {self.query.question}\n\n"
        md += f"**Report ID**: {self.report_id}\n"
        md += f"**Quality Score**: {self.quality_score:.0%}\n"
        md += f"**Sources Used**: {len(self.sources)}\n\n"

        md += "## Executive Summary\n\n"
        md += f"{self.executive_summary}\n\n"

        md += "## Key Findings\n\n"
        for i, finding in enumerate(self.key_findings, 1):
            md += f"{i}. **{finding.claim}** (confidence: {finding.confidence:.0%})\n"
        md += "\n"

        md += "## Sources\n\n"
        for source in self.sources:
            cred = f"[{source.credibility_score:.0%}]"
            url = f" - {source.url}" if source.url else ""
            md += f"- {cred} **{source.title}**{url}\n"

        return md


# =============================================================================
# AgentCore Memory (DynamoDB-backed)
# =============================================================================


class AgentCoreResearchMemory:
    """
    Memory system using DynamoDB for persistence.

    Adapts L26 ResearchMemory to work in AgentCore environment.
    """

    GRAPHITI_GROUP_ID = "research_knowledge"

    def __init__(self, session_id: str, persistence: DynamoDBPersistence | LocalPersistence):
        self.session_id = session_id
        self.persistence = persistence

        # Load existing state or create new
        self.working = self.persistence.load_memory(session_id, "working") or {
            "current_query": None,
            "sources": [],
            "findings": [],
            "context": []
        }
        self.episodic = self.persistence.load_memory(session_id, "episodic") or []
        self.semantic = self.persistence.load_memory(session_id, "semantic") or {}

    def store_working(self, key: str, value: Any):
        """Store in working memory."""
        self.working[key] = value
        self._save()

    def store_episodic(self, event_type: str, content: dict):
        """Store an event in episodic memory."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "content": content
        }
        self.episodic.append(event)
        self._save()

    def store_semantic(self, category: str, fact: str):
        """Store a fact in semantic memory."""
        if category not in self.semantic:
            self.semantic[category] = []
        if fact not in self.semantic[category]:
            self.semantic[category].append(fact)
            self._save()

    def _save(self):
        """Persist all memory layers to DynamoDB."""
        self.persistence.save_all_memory(
            self.session_id,
            working=self.working,
            episodic=self.episodic,
            semantic=self.semantic
        )

    def recall_relevant(self, query: str, budget_tokens: int = 2000) -> str:
        """Retrieve relevant context within token budget."""
        context_parts = []
        used_tokens = 0

        # Priority 1: Working memory
        if self.working.get("current_query"):
            part = f"Current query: {self.working['current_query']}"
            context_parts.append(part)
            used_tokens += len(part.split()) * 1.3

        # Priority 2: Recent episodic
        for event in self.episodic[-3:]:
            if used_tokens > budget_tokens * 0.6:
                break
            part = f"[{event['type']}] {json.dumps(event['content'])[:200]}"
            context_parts.append(part)
            used_tokens += len(part.split()) * 1.3

        # Priority 3: Semantic facts
        query_terms = set(query.lower().split())
        for category, facts in self.semantic.items():
            if used_tokens > budget_tokens * 0.8:
                break
            matching = [f for f in facts if any(t in f.lower() for t in query_terms)]
            for fact in matching[:2]:
                context_parts.append(f"[{category}] {fact}")
                used_tokens += len(fact.split()) * 1.3

        return "\n".join(context_parts)

    def get_stats(self) -> dict:
        return {
            "session_id": self.session_id,
            "working_keys": list(self.working.keys()),
            "episodic_events": len(self.episodic),
            "semantic_categories": len(self.semantic),
        }


# =============================================================================
# Web Search Agent (Configurable Perplexity endpoint)
# =============================================================================


class AgentCoreWebSearchAgent:
    """
    Web search using Perplexity API with configurable endpoint.

    Works in both local (LiteLLM proxy) and AWS (direct Perplexity) environments.
    """

    def __init__(self, model=None):
        self.model = model
        self.search_count = 0
        self.perplexity_config = get_perplexity_config()

    def _real_web_search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Perform web search using Perplexity API."""
        results = []

        if not self.perplexity_config["enabled"]:
            print("    [WebSearch] Perplexity not configured, using LLM fallback")
            return self._llm_knowledge_fallback(query, max_results)

        try:
            payload = {
                "model": self.perplexity_config["model"],
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a research assistant. Search the web and provide comprehensive, well-cited information.

IMPORTANT: Include 8-10 high-quality sources. Prefer:
- Academic papers, research publications
- Official documentation from major tech companies
- Authoritative industry sources (.edu, .gov, arxiv.org)

Format your response as JSON:
{
    "results": [
        {"title": "Source Title", "url": "https://...", "snippet": "Key information...", "credibility": "high|medium"}
    ]
}"""
                    },
                    {
                        "role": "user",
                        "content": f"Research this topic thoroughly with citations: {query}"
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 3000
            }

            response = requests.post(
                self.perplexity_config["base_url"],
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.perplexity_config['api_key']}"
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()

            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Parse JSON results
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                parsed = json.loads(json_match.group())
                for item in parsed.get("results", [])[:max_results]:
                    results.append(SearchResult(
                        title=item.get("title", "Search Result")[:100],
                        url=item.get("url", ""),
                        snippet=item.get("snippet", "")[:500],
                        credibility_hint=item.get("credibility")
                    ))

            if not results and content:
                results.append(SearchResult(
                    title=f"Perplexity Search: {query[:50]}",
                    url="perplexity://search",
                    snippet=content[:500]
                ))

            print(f"    [WebSearch] Found {len(results)} results from Perplexity")

        except requests.RequestException as e:
            print(f"    [WebSearch ERROR] Perplexity failed: {e}")
            results = self._llm_knowledge_fallback(query, max_results)
        except json.JSONDecodeError:
            print(f"    [WebSearch] Perplexity response not JSON")

        return results[:max_results]

    def _llm_knowledge_fallback(self, query: str, max_results: int) -> list[SearchResult]:
        """Fallback to LLM knowledge when Perplexity fails."""
        print(f"    [WebSearch Fallback] Using LLM knowledge...")

        knowledge_agent = Agent(
            model=self.model or get_model_for_environment("fast"),
            system_prompt="""You are a knowledge assistant. Given a query, provide factual information.
Format as JSON: {"results": [{"title": "...", "snippet": "..."}, ...]}""",
            callback_handler=None
        )

        response = str(knowledge_agent(f"Provide factual information about: {query}"))

        results = []
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
                for i, item in enumerate(data.get("results", [])[:max_results]):
                    results.append(SearchResult(
                        title=item.get("title", f"Result {i+1}"),
                        url=f"llm-knowledge://{hashlib.md5(query.encode()).hexdigest()[:8]}/{i}",
                        snippet=item.get("snippet", "")[:500]
                    ))
        except (json.JSONDecodeError, KeyError):
            results.append(SearchResult(
                title=f"LLM Knowledge: {query[:50]}",
                url=f"llm-knowledge://{hashlib.md5(query.encode()).hexdigest()[:8]}",
                snippet=response[:500]
            ))

        return results

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Perform web search."""
        self.search_count += 1
        print(f"    [WebSearch] Searching: {query[:60]}...")
        return self._real_web_search(query, max_results)


# =============================================================================
# Graphiti Integration (Configurable endpoint)
# =============================================================================


class AgentCoreGraphitiClient:
    """
    Graphiti MCP client with configurable endpoint.

    Gracefully degrades if Graphiti is unavailable.
    """

    def __init__(self):
        self.config = get_graphiti_config()
        self.mcp_client = None
        self._initialized = False

    def _ensure_initialized(self):
        """Lazy initialization of MCP client."""
        if self._initialized:
            return

        self._initialized = True

        if not self.config["enabled"]:
            print("[Graphiti] Disabled via configuration")
            return

        try:
            from strands.tools.mcp import MCPClient
            from mcp.client.streamable_http import streamablehttp_client

            # Check if Graphiti is running
            mcp_url = self.config["mcp_url"]
            health_url = mcp_url.replace("/mcp", "/health")

            response = requests.get(health_url, timeout=2)
            if response.status_code == 200:
                self.mcp_client = MCPClient(lambda: streamablehttp_client(mcp_url))
                self.mcp_client.start()
                print(f"[Graphiti] Connected to {mcp_url}")
        except Exception as e:
            print(f"[Graphiti] Not available: {e}")

    @property
    def available(self) -> bool:
        self._ensure_initialized()
        return self.mcp_client is not None

    def add_memory(self, name: str, content: dict, group_id: str = "research_agent"):
        """Add memory to Graphiti."""
        if not self.available:
            return None

        try:
            tool_use_id = f"add-{uuid.uuid4().hex[:8]}"
            result = self.mcp_client.call_tool_sync(
                tool_use_id,
                "add_memory",
                {
                    "name": name,
                    "episode_body": json.dumps(content),
                    "group_id": group_id,
                    "source": "json",
                    "source_description": "AgentCore Research Agent"
                }
            )
            return result
        except Exception as e:
            print(f"[Graphiti ERROR] add_memory failed: {e}")
            return None

    def search_facts(self, query: str, group_ids: list[str] = None, max_facts: int = 5):
        """Search for facts in Graphiti."""
        if not self.available:
            return []

        try:
            tool_use_id = f"search-{uuid.uuid4().hex[:8]}"
            result = self.mcp_client.call_tool_sync(
                tool_use_id,
                "search_memory_facts",
                {
                    "query": query,
                    "group_ids": group_ids or ["research_agent"],
                    "max_facts": max_facts
                }
            )

            results = []
            if result and hasattr(result, 'content'):
                for item in result.content:
                    if hasattr(item, 'text'):
                        try:
                            data = json.loads(item.text)
                            if isinstance(data, list):
                                results.extend(data)
                            elif isinstance(data, dict) and "facts" in data:
                                results.extend(data["facts"])
                        except json.JSONDecodeError:
                            pass
            return results
        except Exception as e:
            print(f"[Graphiti ERROR] search_facts failed: {e}")
            return []


# =============================================================================
# Guardrails (from L22)
# =============================================================================


class AgentCoreGuardrails:
    """Safety layer for research queries and outputs."""

    BLOCKED_PATTERNS = [
        r"how to (make|create|build).*(weapon|bomb|explosive)",
        r"how to (hack|breach|attack)",
        r"(credit card|ssn|social security).*(steal|fraud)",
    ]

    PII_PATTERNS = {
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
        "credit_card": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
    }

    def validate_query(self, query: str) -> tuple[bool, list[str]]:
        """Validate research query for safety."""
        issues = []

        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, query.lower()):
                issues.append(f"Query matches blocked pattern")
                break

        return (len(issues) == 0, issues)

    def redact_pii(self, text: str) -> str:
        """Redact PII from output."""
        result = text
        for pii_type, pattern in self.PII_PATTERNS.items():
            result = re.sub(pattern, f"[REDACTED-{pii_type.upper()}]", result, flags=re.IGNORECASE)
        return result


# =============================================================================
# Research Agent Configuration
# =============================================================================


class AgentCoreResearchConfig(BaseModel):
    """Configuration for the research agent."""
    max_sources: int = 10
    web_search_enabled: bool = True
    quality_threshold: float = 0.60
    max_iterations: int = 2
    enable_learning: bool = True
    graphiti_group_id: str = "research_agent"


# =============================================================================
# Main Research Agent (AgentCore-adapted)
# =============================================================================


class AgentCoreResearchAgent:
    """
    Research agent adapted for AWS Bedrock AgentCore.

    Uses:
    - Bedrock models (Sonnet/Haiku)
    - DynamoDB for persistence
    - External Perplexity for web search
    - External Graphiti for knowledge graph
    """

    def __init__(
        self,
        config: AgentCoreResearchConfig = None,
        session_id: str = None,
        persistence: DynamoDBPersistence | LocalPersistence = None
    ):
        self.config = config or AgentCoreResearchConfig()
        self.session_id = session_id or hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8]
        self.persistence = persistence or get_persistence()

        # Initialize models
        self.fast_model = get_model_for_environment("fast")
        self.reasoning_model = get_model_for_environment("reasoning")

        # Initialize components
        self.memory = AgentCoreResearchMemory(self.session_id, self.persistence)
        self.web_search = AgentCoreWebSearchAgent(self.fast_model)
        self.graphiti = AgentCoreGraphitiClient()
        self.guardrails = AgentCoreGuardrails()

        print(f"  [AgentCore] Research Agent initialized (session: {self.session_id})")

    def research(self, question: str, **kwargs) -> ResearchReport:
        """
        Execute research and return report.

        Args:
            question: Research question
            **kwargs: Additional options (scope, max_sources)

        Returns:
            ResearchReport with findings
        """
        print(f"\n  Starting research: {question[:50]}...")

        # 1. Validate query
        is_valid, issues = self.guardrails.validate_query(question)
        if not is_valid:
            raise ValueError(f"Query blocked: {issues}")

        # 2. Create query object
        query = ResearchQuery(
            question=question,
            scope=ResearchScope(kwargs.get("scope", "medium")),
            max_sources=kwargs.get("max_sources", self.config.max_sources)
        )

        # 3. Store in memory
        self.memory.store_working("current_query", question)

        # 4. Save checkpoint
        self.persistence.save_checkpoint(
            query.query_id,
            "start",
            {"query": query.model_dump()}
        )

        # 5. Search for sources
        print("    Searching for sources...")
        search_results = self.web_search.search(question, max_results=query.max_sources)

        # 6. Convert to sources
        sources = []
        for result in search_results:
            cred_score = 0.8 if result.credibility_hint == "high" else 0.6
            sources.append(ResearchSource(
                title=result.title,
                url=result.url,
                source_type=result.source_type,
                credibility_score=cred_score,
                content_summary=result.snippet
            ))

        # 7. Store event
        self.memory.store_episodic("search", {"query": question, "results": len(sources)})

        # 8. Extract findings
        print("    Extracting findings...")
        findings = self._extract_findings(sources, question)

        # 9. Generate summary
        print("    Generating summary...")
        summary = self._generate_summary(question, findings)

        # 10. Compile report
        report = ResearchReport(
            query=query,
            executive_summary=summary,
            key_findings=findings,
            sources=sources,
            methodology="Web search with Bedrock synthesis",
            quality_score=self._estimate_quality(findings, sources)
        )

        # 11. Redact PII from output
        report.executive_summary = self.guardrails.redact_pii(report.executive_summary)

        # 12. Persist to Graphiti if enabled
        if self.config.enable_learning and self.graphiti.available:
            self.graphiti.add_memory(
                f"research_{report.report_id}",
                {
                    "query": question,
                    "findings_count": len(findings),
                    "sources_count": len(sources),
                    "quality_score": report.quality_score
                },
                self.config.graphiti_group_id
            )

        # 13. Save final checkpoint
        self.persistence.save_checkpoint(
            query.query_id,
            "complete",
            {"report_id": report.report_id, "quality": report.quality_score}
        )

        print(f"  Research complete: {len(findings)} findings, {len(sources)} sources")
        return report

    def _extract_findings(self, sources: list[ResearchSource], question: str) -> list[ResearchFinding]:
        """Extract key findings from sources using LLM."""
        findings = []

        if not sources:
            return findings

        # Combine source content
        source_text = "\n".join([
            f"Source: {s.title}\n{s.content_summary}"
            for s in sources[:5]
        ])

        extraction_agent = Agent(
            model=self.reasoning_model,
            system_prompt="""Extract key findings from the sources. Format as JSON:
{"findings": [{"claim": "Finding statement", "confidence": 0.8, "category": "technical"}, ...]}""",
            callback_handler=None
        )

        prompt = f"Question: {question}\n\nSources:\n{source_text}\n\nExtract 3-5 key findings."

        try:
            response = str(extraction_agent(prompt))
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
                for item in data.get("findings", []):
                    findings.append(ResearchFinding(
                        claim=item.get("claim", ""),
                        confidence=item.get("confidence", 0.7),
                        category=item.get("category", "general"),
                        supporting_sources=[s.source_id for s in sources[:2]]
                    ))
        except Exception as e:
            print(f"    [Extract ERROR] {e}")
            # Fallback: create simple finding
            findings.append(ResearchFinding(
                claim=f"Research on: {question[:50]}",
                confidence=0.5,
                category="general"
            ))

        return findings

    def _generate_summary(self, question: str, findings: list[ResearchFinding]) -> str:
        """Generate executive summary."""
        if not findings:
            return f"Research on '{question}' did not yield sufficient findings."

        findings_text = "\n".join([f"- {f.claim}" for f in findings])

        summary_agent = Agent(
            model=self.fast_model,
            system_prompt="You are a research summarizer. Write a concise 2-3 sentence executive summary.",
            callback_handler=None
        )

        response = str(summary_agent(f"Question: {question}\n\nFindings:\n{findings_text}\n\nWrite executive summary:"))
        return response[:500]

    def _estimate_quality(self, findings: list[ResearchFinding], sources: list[ResearchSource]) -> float:
        """Estimate report quality heuristically."""
        score = 0.0

        # Findings score (40%)
        finding_count = len(findings)
        score += min(finding_count / 5, 1.0) * 0.4

        # Source score (30%)
        source_count = len(sources)
        score += min(source_count / 10, 1.0) * 0.3

        # Credibility score (30%)
        if sources:
            avg_cred = sum(s.credibility_score for s in sources) / len(sources)
            score += avg_cred * 0.3

        return min(score, 1.0)


# =============================================================================
# FastAPI Application (AgentCore Endpoints)
# =============================================================================

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel as PydanticBaseModel
import uvicorn


# Global persistence (initialized on startup)
_persistence = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    global _persistence
    _persistence = get_persistence()
    print(f"[Startup] Persistence: {type(_persistence).__name__}")
    print(f"[Startup] Environment: {'AWS' if is_aws_environment() else 'Local'}")
    yield
    # Cleanup on shutdown (if needed)
    print("[Shutdown] Research Agent stopping")


app = FastAPI(
    title="Research Agent - AgentCore",
    version="L27",
    description="Research Agent for AWS Bedrock AgentCore",
    lifespan=lifespan
)


class InvocationRequest(PydanticBaseModel):
    """AgentCore invocation request."""
    input: dict  # {"prompt": "...", "session_id": "..."}


class InvocationResponse(PydanticBaseModel):
    """AgentCore invocation response."""
    output: dict


@app.post("/invocations", response_model=InvocationResponse)
async def invoke_agent(request: InvocationRequest):
    """
    AgentCore-compatible invocation endpoint.

    Request format:
        {"input": {"prompt": "Research question here", "session_id": "optional-id"}}

    Response format:
        {"output": {"report_id": "...", "quality_score": 0.8, "executive_summary": "...", ...}}
    """
    try:
        prompt = request.input.get("prompt", "")
        session_id = request.input.get("session_id", str(uuid.uuid4())[:8])

        if not prompt:
            raise HTTPException(status_code=400, detail="No prompt provided")

        # Create agent
        config = AgentCoreResearchConfig(
            enable_learning=os.environ.get("ENABLE_GRAPHITI", "true").lower() == "true",
            web_search_enabled=os.environ.get("ENABLE_PERPLEXITY", "true").lower() == "true",
        )
        agent = AgentCoreResearchAgent(
            config=config,
            session_id=session_id,
            persistence=_persistence
        )

        # Execute research
        report = agent.research(prompt)

        return InvocationResponse(output={
            "report_id": report.report_id,
            "quality_score": report.quality_score,
            "executive_summary": report.executive_summary,
            "findings_count": len(report.key_findings),
            "sources_count": len(report.sources),
            "markdown": report.to_markdown()
        })

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ping")
async def ping():
    """AgentCore health check endpoint."""
    return {"status": "healthy"}


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Research Agent",
        "version": "L27",
        "environment": "AWS" if is_aws_environment() else "Local",
        "endpoints": {
            "POST /invocations": "Execute research",
            "GET /ping": "Health check"
        }
    }


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("Level 27: Research Agent for AWS Bedrock AgentCore")
    print("=" * 70)

    # Check if running demo or server
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        # Run demo
        print("\n--- Demo Mode ---\n")
        persistence = LocalPersistence()
        agent = AgentCoreResearchAgent(
            session_id="demo-session",
            persistence=persistence
        )

        report = agent.research("What are the differences between RAG and fine-tuning?")

        print("\n--- Report ---")
        print(report.to_markdown())

    else:
        # Run server
        print("\nStarting FastAPI server on port 8080...")
        print("Endpoints:")
        print("  POST /invocations - Execute research")
        print("  GET /ping - Health check")
        print("  GET / - API info")
        print("\nPress Ctrl+C to stop.\n")

        uvicorn.run(app, host="0.0.0.0", port=8080)
