"""
Level 23: Error Recovery

Production-ready error recovery for Strands Agents with:
- Retry with exponential backoff
- Failure detection and classification
- Retry policies (strategy pattern)
- Fallback chains (model, service, graceful degradation)
- Circuit breaker pattern
- Checkpoint and resume
- Human escalation
- AWS SQS Dead-Letter Queues
- AWS Step Functions retry patterns
- Unified RecoveryStack

10 Iterations:
1. Basic Retry with Exponential Backoff
2. Failure Detection & Classification
3. Retry Policies (Strategy Pattern)
4. Fallback Chains
5. Circuit Breaker Pattern
6. Checkpoint & Resume
7. Human Escalation
8. AWS SQS Dead-Letter Queues
9. AWS Step Functions Retry
10. Unified RecoveryStack
"""

import json
import random
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any, Callable, Generic, TypeVar

from pydantic import BaseModel

# ============================================================================
# ITERATION 1: Basic Retry with Exponential Backoff
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 1: Basic Retry with Exponential Backoff")
print("=" * 70)


@dataclass
class RetryConfig:
    """Configuration for retry behavior with exponential backoff.

    Attributes:
        max_retries: Maximum number of retry attempts (0 = no retries)
        base_delay: Initial delay in seconds before first retry
        max_delay: Maximum delay cap in seconds
        jitter: Random jitter factor (0.0-1.0) to prevent thundering herd
        exponential_base: Base for exponential calculation (default 2)
    """
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: float = 0.1
    exponential_base: float = 2.0

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for a given attempt number.

        Formula: min(base_delay * (exponential_base ^ attempt) + jitter, max_delay)

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds with jitter applied
        """
        # Exponential delay
        delay = self.base_delay * (self.exponential_base ** attempt)

        # Apply jitter (random value between -jitter and +jitter of delay)
        if self.jitter > 0:
            jitter_amount = delay * self.jitter * random.uniform(-1, 1)
            delay += jitter_amount

        # Cap at max_delay
        return min(max(0, delay), self.max_delay)


@dataclass
class RetryResult:
    """Result of a retry operation.

    Attributes:
        success: Whether the operation ultimately succeeded
        result: The successful result (if success=True)
        error: The final error (if success=False)
        attempts: Total number of attempts made
        total_delay: Total time spent in delays
        history: List of (attempt, error, delay) for each failed attempt
    """
    success: bool
    result: Any = None
    error: Exception | None = None
    attempts: int = 0
    total_delay: float = 0.0
    history: list[tuple[int, str, float]] = field(default_factory=list)


class RetryExecutor:
    """Execute operations with retry logic and exponential backoff.

    Example:
        >>> config = RetryConfig(max_retries=3, base_delay=1.0)
        >>> executor = RetryExecutor(config)
        >>> result = executor.execute(my_flaky_function, arg1, arg2)
        >>> if result.success:
        ...     print(f"Success after {result.attempts} attempts")
    """

    def __init__(self, config: RetryConfig | None = None):
        self.config = config or RetryConfig()

    def execute(
        self,
        func: Callable,
        *args,
        retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
        **kwargs
    ) -> RetryResult:
        """Execute a function with retry logic.

        Args:
            func: The function to execute
            *args: Positional arguments for the function
            retryable_exceptions: Tuple of exception types that should trigger retry
            **kwargs: Keyword arguments for the function

        Returns:
            RetryResult with success status, result/error, and attempt history
        """
        history: list[tuple[int, str, float]] = []
        total_delay = 0.0
        last_error: Exception | None = None

        for attempt in range(self.config.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                return RetryResult(
                    success=True,
                    result=result,
                    attempts=attempt + 1,
                    total_delay=total_delay,
                    history=history
                )
            except retryable_exceptions as e:
                last_error = e

                # Don't delay after the last attempt
                if attempt < self.config.max_retries:
                    delay = self.config.calculate_delay(attempt)
                    history.append((attempt + 1, str(e), delay))
                    total_delay += delay
                    print(f"  Attempt {attempt + 1} failed: {e}")
                    print(f"  Retrying in {delay:.2f}s...")
                    time.sleep(delay)
                else:
                    history.append((attempt + 1, str(e), 0.0))

        return RetryResult(
            success=False,
            error=last_error,
            attempts=self.config.max_retries + 1,
            total_delay=total_delay,
            history=history
        )


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: float = 0.1,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)
) -> Callable:
    """Decorator for adding retry with exponential backoff to any function.

    Example:
        >>> @retry_with_backoff(max_retries=3, base_delay=0.5)
        ... def fetch_data(url: str) -> dict:
        ...     return requests.get(url).json()
    """
    config = RetryConfig(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay,
        jitter=jitter
    )
    executor = RetryExecutor(config)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            result = executor.execute(
                func, *args,
                retryable_exceptions=retryable_exceptions,
                **kwargs
            )
            if result.success:
                return result.result
            raise result.error  # type: ignore
        return wrapper
    return decorator


# Demo Iteration 1
print("\nDemo: Retry with Exponential Backoff")
print("-" * 40)

# Simulate a flaky API call
call_count = 0

def flaky_api_call(succeed_after: int = 3) -> str:
    """Simulates an API that fails a few times before succeeding."""
    global call_count
    call_count += 1
    if call_count < succeed_after:
        raise ConnectionError(f"Connection refused (attempt {call_count})")
    return f"Success on attempt {call_count}!"

# Test 1: Function that succeeds after 2 failures
print("\nTest 1: Retry succeeds after transient failures")
call_count = 0
config = RetryConfig(max_retries=5, base_delay=0.1, jitter=0.0)  # Fast for demo
executor = RetryExecutor(config)
result = executor.execute(flaky_api_call, succeed_after=3)
print(f"  Result: {result.success}")
print(f"  Value: {result.result}")
print(f"  Attempts: {result.attempts}")
print(f"  Total delay: {result.total_delay:.2f}s")

# Test 2: Function that never succeeds (exhausts retries)
print("\nTest 2: Retry exhausted - all attempts fail")
call_count = 0
config = RetryConfig(max_retries=2, base_delay=0.1, jitter=0.0)
executor = RetryExecutor(config)
result = executor.execute(flaky_api_call, succeed_after=10)
print(f"  Result: {result.success}")
print(f"  Error: {result.error}")
print(f"  Attempts: {result.attempts}")
print(f"  History: {result.history}")

# Test 3: Decorator usage
print("\nTest 3: Decorator usage")
call_count = 0

@retry_with_backoff(max_retries=3, base_delay=0.1, jitter=0.0)
def decorated_api_call() -> str:
    global call_count
    call_count += 1
    if call_count < 2:
        raise TimeoutError("Request timed out")
    return "Decorated success!"

try:
    result = decorated_api_call()
    print(f"  Result: {result}")
except Exception as e:
    print(f"  Failed: {e}")

# Test 4: Delay calculation visualization
print("\nTest 4: Exponential backoff delay progression")
config = RetryConfig(max_retries=6, base_delay=1.0, max_delay=30.0, jitter=0.0)
print("  Attempt | Delay (seconds)")
print("  --------|----------------")
for attempt in range(7):
    delay = config.calculate_delay(attempt)
    bar = "#" * int(delay)
    print(f"  {attempt + 1:>7} | {delay:>6.2f}s {bar}")

print("\n  Key insight: Exponential growth (1s -> 2s -> 4s -> 8s -> 16s -> 30s cap)")


# ============================================================================
# ITERATION 2: Failure Detection & Classification
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 2: Failure Detection & Classification")
print("=" * 70)


class FailureType(Enum):
    """Classification of failure types for retry decisions.

    TRANSIENT: Temporary failures that may succeed on retry
    PERMANENT: Failures that will not recover with retry
    RATE_LIMITED: Server is throttling requests
    TIMEOUT: Request timed out (network or server)
    RESOURCE_EXHAUSTED: Out of memory, disk, quota
    AUTHENTICATION: Auth/authz failure
    VALIDATION: Invalid input/request
    UNKNOWN: Cannot classify
    """
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    AUTHENTICATION = "authentication"
    VALIDATION = "validation"
    UNKNOWN = "unknown"


@dataclass
class ClassifiedFailure:
    """A failure with classification metadata.

    Attributes:
        failure_type: The classified type of failure
        error: The original exception
        message: Error message
        http_code: HTTP status code if applicable
        retryable: Whether this failure type is retryable
        suggested_delay: Recommended delay before retry (if retryable)
        confidence: Classification confidence (0.0-1.0)
    """
    failure_type: FailureType
    error: Exception
    message: str
    http_code: int | None = None
    retryable: bool = True
    suggested_delay: float | None = None
    confidence: float = 1.0


class FailureClassifier:
    """Classify failures to determine retry strategy.

    Uses pattern matching on error messages, exception types,
    and HTTP status codes to classify failures.
    """

    # Keyword patterns for each failure type
    PATTERNS: dict[FailureType, list[str]] = {
        FailureType.TRANSIENT: [
            "connection refused", "connection reset", "connection error",
            "temporary", "temporarily unavailable", "try again",
            "service unavailable", "internal server error", "bad gateway",
            "network error", "network unreachable", "ECONNREFUSED"
        ],
        FailureType.RATE_LIMITED: [
            "rate limit", "rate-limit", "ratelimit", "throttl",
            "too many requests", "quota exceeded", "slow down",
            "429", "retry-after"
        ],
        FailureType.TIMEOUT: [
            "timeout", "timed out", "deadline exceeded",
            "request timeout", "gateway timeout", "read timeout",
            "connect timeout", "ETIMEDOUT"
        ],
        FailureType.RESOURCE_EXHAUSTED: [
            "out of memory", "oom", "memory error", "disk full",
            "no space left", "quota", "resource exhausted",
            "insufficient resources", "capacity"
        ],
        FailureType.AUTHENTICATION: [
            "unauthorized", "authentication", "not authenticated",
            "invalid credentials", "access denied", "forbidden",
            "401", "403", "invalid token", "expired token"
        ],
        FailureType.VALIDATION: [
            "invalid", "validation", "bad request", "malformed",
            "missing required", "not found", "400", "404",
            "unprocessable", "422"
        ],
        FailureType.PERMANENT: [
            "not implemented", "unsupported", "deprecated",
            "permanently", "gone", "410", "501"
        ]
    }

    # HTTP status code mappings
    HTTP_CODES: dict[int, FailureType] = {
        400: FailureType.VALIDATION,
        401: FailureType.AUTHENTICATION,
        403: FailureType.AUTHENTICATION,
        404: FailureType.VALIDATION,
        408: FailureType.TIMEOUT,
        410: FailureType.PERMANENT,
        422: FailureType.VALIDATION,
        429: FailureType.RATE_LIMITED,
        500: FailureType.TRANSIENT,
        502: FailureType.TRANSIENT,
        503: FailureType.TRANSIENT,
        504: FailureType.TIMEOUT,
    }

    # Which failure types are retryable
    RETRYABLE: set[FailureType] = {
        FailureType.TRANSIENT,
        FailureType.RATE_LIMITED,
        FailureType.TIMEOUT,
        FailureType.RESOURCE_EXHAUSTED,  # Sometimes recoverable
        FailureType.UNKNOWN,  # Try once more
    }

    # Suggested delays by failure type
    SUGGESTED_DELAYS: dict[FailureType, float] = {
        FailureType.TRANSIENT: 1.0,
        FailureType.RATE_LIMITED: 5.0,  # Back off more for rate limits
        FailureType.TIMEOUT: 2.0,
        FailureType.RESOURCE_EXHAUSTED: 10.0,  # Wait for resources
        FailureType.UNKNOWN: 1.0,
    }

    def classify(
        self,
        error: Exception,
        http_code: int | None = None
    ) -> ClassifiedFailure:
        """Classify a failure for retry decision making.

        Args:
            error: The exception to classify
            http_code: HTTP status code if available

        Returns:
            ClassifiedFailure with type, retryability, and suggestions
        """
        message = str(error).lower()

        # Check HTTP code first (highest confidence)
        if http_code and http_code in self.HTTP_CODES:
            failure_type = self.HTTP_CODES[http_code]
            return ClassifiedFailure(
                failure_type=failure_type,
                error=error,
                message=str(error),
                http_code=http_code,
                retryable=failure_type in self.RETRYABLE,
                suggested_delay=self.SUGGESTED_DELAYS.get(failure_type),
                confidence=0.95
            )

        # Check exception type
        exception_type = self._classify_by_exception_type(error)
        if exception_type:
            return ClassifiedFailure(
                failure_type=exception_type,
                error=error,
                message=str(error),
                retryable=exception_type in self.RETRYABLE,
                suggested_delay=self.SUGGESTED_DELAYS.get(exception_type),
                confidence=0.85
            )

        # Pattern matching on message
        for failure_type, patterns in self.PATTERNS.items():
            for pattern in patterns:
                if pattern in message:
                    return ClassifiedFailure(
                        failure_type=failure_type,
                        error=error,
                        message=str(error),
                        retryable=failure_type in self.RETRYABLE,
                        suggested_delay=self.SUGGESTED_DELAYS.get(failure_type),
                        confidence=0.7
                    )

        # Unknown - default to potentially retryable
        return ClassifiedFailure(
            failure_type=FailureType.UNKNOWN,
            error=error,
            message=str(error),
            retryable=True,
            suggested_delay=1.0,
            confidence=0.3
        )

    def _classify_by_exception_type(self, error: Exception) -> FailureType | None:
        """Classify based on Python exception type."""
        exception_map: dict[type, FailureType] = {
            TimeoutError: FailureType.TIMEOUT,
            ConnectionError: FailureType.TRANSIENT,
            ConnectionRefusedError: FailureType.TRANSIENT,
            ConnectionResetError: FailureType.TRANSIENT,
            MemoryError: FailureType.RESOURCE_EXHAUSTED,
            PermissionError: FailureType.AUTHENTICATION,
            FileNotFoundError: FailureType.VALIDATION,
            ValueError: FailureType.VALIDATION,
            KeyError: FailureType.VALIDATION,
        }

        for exc_type, failure_type in exception_map.items():
            if isinstance(error, exc_type):
                return failure_type
        return None


# Demo Iteration 2
print("\nDemo: Failure Classification")
print("-" * 40)

classifier = FailureClassifier()

test_errors = [
    (ConnectionError("Connection refused by server"), None),
    (TimeoutError("Request timed out after 30s"), None),
    (Exception("Rate limit exceeded. Retry after 60s"), None),
    (ValueError("Invalid parameter: name is required"), None),
    (Exception("401 Unauthorized: Invalid API key"), 401),
    (Exception("Internal Server Error"), 500),
    (Exception("Service temporarily unavailable"), 503),
    (MemoryError("Out of memory"), None),
    (Exception("Something weird happened"), None),
]

print("\nClassification Results:")
print("-" * 70)
print(f"{'Error':<35} {'Type':<18} {'Retryable':<10} {'Conf':<6}")
print("-" * 70)

for error, http_code in test_errors:
    result = classifier.classify(error, http_code)
    error_str = str(error)[:33] + ".." if len(str(error)) > 35 else str(error)
    print(f"{error_str:<35} {result.failure_type.value:<18} {str(result.retryable):<10} {result.confidence:.2f}")

print("\n  Key insight: Classification enables smart retry decisions")
print("  - TRANSIENT/TIMEOUT/RATE_LIMITED: Retry with appropriate delay")
print("  - VALIDATION/AUTHENTICATION: Don't retry (will always fail)")
print("  - UNKNOWN: Retry once, then fail fast")


# ============================================================================
# ITERATION 3: Retry Policies (Strategy Pattern)
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 3: Retry Policies (Strategy Pattern)")
print("=" * 70)


class RetryPolicy(ABC):
    """Base class for retry policies.

    Policies determine whether a retry should be attempted based on
    the failure classification and attempt history.
    """

    @abstractmethod
    def should_retry(
        self,
        failure: ClassifiedFailure,
        attempt: int,
        max_attempts: int
    ) -> tuple[bool, float | None]:
        """Determine if a retry should be attempted.

        Args:
            failure: The classified failure
            attempt: Current attempt number (1-indexed)
            max_attempts: Maximum attempts allowed

        Returns:
            Tuple of (should_retry, suggested_delay)
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Policy name for logging."""
        pass


class AlwaysRetryPolicy(RetryPolicy):
    """Always retry up to max attempts, regardless of failure type."""

    @property
    def name(self) -> str:
        return "AlwaysRetry"

    def should_retry(
        self,
        failure: ClassifiedFailure,
        attempt: int,
        max_attempts: int
    ) -> tuple[bool, float | None]:
        if attempt < max_attempts:
            return True, failure.suggested_delay
        return False, None


class TransientOnlyPolicy(RetryPolicy):
    """Only retry transient failures; fail fast on permanent errors."""

    @property
    def name(self) -> str:
        return "TransientOnly"

    def should_retry(
        self,
        failure: ClassifiedFailure,
        attempt: int,
        max_attempts: int
    ) -> tuple[bool, float | None]:
        if attempt >= max_attempts:
            return False, None

        if not failure.retryable:
            return False, None

        return True, failure.suggested_delay


class BudgetAwarePolicy(RetryPolicy):
    """Stop retrying if cumulative cost exceeds budget.

    Useful for LLM calls where each retry costs money.
    """

    def __init__(self, max_cost: float, cost_per_attempt: float = 0.01):
        self.max_cost = max_cost
        self.cost_per_attempt = cost_per_attempt
        self.spent = 0.0

    @property
    def name(self) -> str:
        return f"BudgetAware(max=${self.max_cost})"

    def should_retry(
        self,
        failure: ClassifiedFailure,
        attempt: int,
        max_attempts: int
    ) -> tuple[bool, float | None]:
        # Track cost of this attempt
        self.spent += self.cost_per_attempt

        if attempt >= max_attempts:
            return False, None

        if not failure.retryable:
            return False, None

        # Check budget
        if self.spent + self.cost_per_attempt > self.max_cost:
            return False, None

        return True, failure.suggested_delay

    def reset(self):
        """Reset spent amount for new operation."""
        self.spent = 0.0


class AdaptivePolicy(RetryPolicy):
    """Adapt retry behavior based on failure patterns.

    - Increases delay for rate limits
    - Reduces max retries for repeated permanent failures
    - Tracks failure history for better decisions
    """

    def __init__(self, base_max_attempts: int = 3):
        self.base_max_attempts = base_max_attempts
        self.failure_history: list[FailureType] = []
        self.consecutive_rate_limits = 0

    @property
    def name(self) -> str:
        return "Adaptive"

    def should_retry(
        self,
        failure: ClassifiedFailure,
        attempt: int,
        max_attempts: int
    ) -> tuple[bool, float | None]:
        self.failure_history.append(failure.failure_type)

        # Track consecutive rate limits
        if failure.failure_type == FailureType.RATE_LIMITED:
            self.consecutive_rate_limits += 1
        else:
            self.consecutive_rate_limits = 0

        if attempt >= max_attempts:
            return False, None

        if not failure.retryable:
            return False, None

        # Calculate adaptive delay
        delay = failure.suggested_delay or 1.0

        # Exponentially increase delay for rate limits
        if failure.failure_type == FailureType.RATE_LIMITED:
            delay *= (2 ** self.consecutive_rate_limits)
            delay = min(delay, 60.0)  # Cap at 60s

        # If we've seen many failures, reduce remaining attempts
        recent_failures = self.failure_history[-5:]
        if len(recent_failures) >= 3 and all(
            f == FailureType.TRANSIENT for f in recent_failures
        ):
            # System might be down, don't keep hammering
            delay *= 2

        return True, delay

    def reset(self):
        """Reset state for new operation."""
        self.failure_history.clear()
        self.consecutive_rate_limits = 0


class PolicyBasedRetryExecutor:
    """Execute operations with policy-based retry decisions."""

    def __init__(
        self,
        config: RetryConfig,
        policy: RetryPolicy,
        classifier: FailureClassifier | None = None
    ):
        self.config = config
        self.policy = policy
        self.classifier = classifier or FailureClassifier()

    def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> RetryResult:
        """Execute with policy-based retry logic."""
        history: list[tuple[int, str, float]] = []
        total_delay = 0.0
        last_error: Exception | None = None

        for attempt in range(1, self.config.max_retries + 2):  # +2 for 1-indexed and initial
            try:
                result = func(*args, **kwargs)
                return RetryResult(
                    success=True,
                    result=result,
                    attempts=attempt,
                    total_delay=total_delay,
                    history=history
                )
            except Exception as e:
                last_error = e
                failure = self.classifier.classify(e)

                should_retry, suggested_delay = self.policy.should_retry(
                    failure, attempt, self.config.max_retries + 1
                )

                if should_retry:
                    delay = suggested_delay or self.config.calculate_delay(attempt - 1)
                    history.append((attempt, str(e), delay))
                    total_delay += delay
                    print(f"  [{self.policy.name}] Attempt {attempt} failed: {failure.failure_type.value}")
                    print(f"  Retrying in {delay:.2f}s...")
                    time.sleep(delay)
                else:
                    history.append((attempt, str(e), 0.0))
                    print(f"  [{self.policy.name}] Attempt {attempt} failed: {failure.failure_type.value}")
                    print(f"  Policy says: NO RETRY")
                    break

        return RetryResult(
            success=False,
            error=last_error,
            attempts=len(history),
            total_delay=total_delay,
            history=history
        )


# Demo Iteration 3
print("\nDemo: Retry Policies")
print("-" * 40)

# Simulate different failure scenarios
def simulate_failure(failure_type: str, succeed_after: int = 3) -> Callable:
    """Create a function that fails with specific error types."""
    call_count = 0

    def failing_func() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < succeed_after:
            if failure_type == "transient":
                raise ConnectionError("Connection refused")
            elif failure_type == "rate_limit":
                raise Exception("Rate limit exceeded")
            elif failure_type == "auth":
                raise PermissionError("Invalid credentials")
            elif failure_type == "timeout":
                raise TimeoutError("Request timed out")
        return f"Success after {call_count} attempts"

    return failing_func

config = RetryConfig(max_retries=4, base_delay=0.1, jitter=0.0)

# Test 1: AlwaysRetry with auth failure (wastes retries)
print("\nTest 1: AlwaysRetry with authentication failure")
print("  (Will waste retries on non-recoverable error)")
executor = PolicyBasedRetryExecutor(config, AlwaysRetryPolicy())
result = executor.execute(simulate_failure("auth", succeed_after=10))
print(f"  Result: {result.success}, Attempts: {result.attempts}")

# Test 2: TransientOnly with auth failure (fails fast)
print("\nTest 2: TransientOnly with authentication failure")
print("  (Should fail immediately)")
executor = PolicyBasedRetryExecutor(config, TransientOnlyPolicy())
result = executor.execute(simulate_failure("auth", succeed_after=10))
print(f"  Result: {result.success}, Attempts: {result.attempts}")

# Test 3: TransientOnly with transient failure (retries and succeeds)
print("\nTest 3: TransientOnly with transient failure")
print("  (Should retry and succeed)")
executor = PolicyBasedRetryExecutor(config, TransientOnlyPolicy())
result = executor.execute(simulate_failure("transient", succeed_after=3))
print(f"  Result: {result.success}, Attempts: {result.attempts}")

# Test 4: BudgetAware stops when cost exceeded
print("\nTest 4: BudgetAware with limited budget")
print("  (Should stop when budget exhausted)")
budget_policy = BudgetAwarePolicy(max_cost=0.025, cost_per_attempt=0.01)
executor = PolicyBasedRetryExecutor(config, budget_policy)
result = executor.execute(simulate_failure("transient", succeed_after=10))
print(f"  Result: {result.success}, Attempts: {result.attempts}")
print(f"  Spent: ${budget_policy.spent:.3f}")

# Test 5: Adaptive with rate limits
print("\nTest 5: Adaptive with rate limit failures")
print("  (Should increase delays for repeated rate limits)")
adaptive_policy = AdaptivePolicy()
executor = PolicyBasedRetryExecutor(config, adaptive_policy)

# Track delays
delays = []
original_sleep = time.sleep
def tracking_sleep(duration):
    delays.append(duration)
    # Don't actually sleep in demo
time.sleep = tracking_sleep

result = executor.execute(simulate_failure("rate_limit", succeed_after=10))
time.sleep = original_sleep

print(f"  Delays: {[f'{d:.2f}s' for d in delays]}")
print("  Note: Delays increase exponentially for rate limits")

print("\n  Key insight: Right policy for right scenario")
print("  - AlwaysRetry: Simple, but wastes resources on permanent failures")
print("  - TransientOnly: Efficient, fails fast on non-recoverable errors")
print("  - BudgetAware: Cost control for expensive operations (LLM calls)")
print("  - Adaptive: Smart, learns from failure patterns")


# ============================================================================
# ITERATION 4: Fallback Chains
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 4: Fallback Chains")
print("=" * 70)

T = TypeVar('T')


@dataclass
class FallbackResult(Generic[T]):
    """Result of a fallback chain execution.

    Attributes:
        success: Whether any option succeeded
        result: The successful result
        used_fallback: Which fallback was used (0 = primary)
        fallback_name: Name of the successful option
        attempts: List of (name, error) for failed attempts
    """
    success: bool
    result: T | None = None
    used_fallback: int = 0
    fallback_name: str = ""
    attempts: list[tuple[str, str]] = field(default_factory=list)


class FallbackChain(Generic[T]):
    """Execute a chain of fallback options until one succeeds.

    Example:
        >>> chain = FallbackChain[str]()
        >>> chain.add("primary", call_primary_api)
        >>> chain.add("backup", call_backup_api)
        >>> chain.add("cache", get_from_cache)
        >>> result = chain.execute()
    """

    def __init__(self):
        self.options: list[tuple[str, Callable[[], T]]] = []

    def add(self, name: str, func: Callable[[], T]) -> "FallbackChain[T]":
        """Add a fallback option to the chain."""
        self.options.append((name, func))
        return self

    def execute(self) -> FallbackResult[T]:
        """Execute the chain, trying each option until success."""
        attempts: list[tuple[str, str]] = []

        for i, (name, func) in enumerate(self.options):
            try:
                result = func()
                return FallbackResult(
                    success=True,
                    result=result,
                    used_fallback=i,
                    fallback_name=name,
                    attempts=attempts
                )
            except Exception as e:
                attempts.append((name, str(e)))
                print(f"  [{name}] Failed: {e}")

        return FallbackResult(
            success=False,
            result=None,
            attempts=attempts
        )


class ModelFallbackChain:
    """Specialized fallback chain for LLM model selection.

    Automatically falls back to cheaper/faster models when
    primary model is unavailable or rate limited.
    """

    # Model hierarchy: most capable -> least capable
    DEFAULT_FALLBACKS: list[tuple[str, float]] = [
        ("claude-opus-4", 0.015),       # Most capable, most expensive
        ("claude-sonnet-4", 0.003),     # Balanced
        ("claude-3-5-haiku", 0.00025),  # Fast, cheap
        ("gemini-2.0-flash", 0.0001),   # Very fast, very cheap
    ]

    def __init__(
        self,
        model_caller: Callable[[str, str], str],
        models: list[tuple[str, float]] | None = None
    ):
        """
        Args:
            model_caller: Function(model_id, prompt) -> response
            models: List of (model_id, cost_per_1k_tokens)
        """
        self.model_caller = model_caller
        self.models = models or self.DEFAULT_FALLBACKS

    def call(self, prompt: str) -> tuple[str, str, float]:
        """Call with automatic model fallback.

        Returns:
            Tuple of (response, model_used, cost_per_1k)
        """
        errors = []

        for model_id, cost in self.models:
            try:
                response = self.model_caller(model_id, prompt)
                return response, model_id, cost
            except Exception as e:
                errors.append((model_id, str(e)))
                print(f"  [{model_id}] Failed: {e}")

        raise RuntimeError(f"All models failed: {errors}")


class GracefulDegradation:
    """Degrade response quality gracefully on failures.

    Tiers:
    1. Full response (complete, detailed)
    2. Summary response (abbreviated)
    3. Cached response (possibly stale)
    4. Error message (informative failure)
    """

    def __init__(
        self,
        full_handler: Callable[[], str],
        summary_handler: Callable[[], str] | None = None,
        cache_handler: Callable[[], str] | None = None,
        error_message: str = "Service temporarily unavailable"
    ):
        self.full_handler = full_handler
        self.summary_handler = summary_handler
        self.cache_handler = cache_handler
        self.error_message = error_message

    def execute(self) -> tuple[str, str]:
        """Execute with graceful degradation.

        Returns:
            Tuple of (response, quality_tier)
        """
        # Try full response
        try:
            return self.full_handler(), "full"
        except Exception as e:
            print(f"  [full] Failed: {e}")

        # Try summary
        if self.summary_handler:
            try:
                return self.summary_handler(), "summary"
            except Exception as e:
                print(f"  [summary] Failed: {e}")

        # Try cache
        if self.cache_handler:
            try:
                return self.cache_handler(), "cached"
            except Exception as e:
                print(f"  [cache] Failed: {e}")

        # Return error message
        return self.error_message, "error"


# Demo Iteration 4
print("\nDemo: Fallback Chains")
print("-" * 40)

# Test 1: Basic fallback chain
print("\nTest 1: Service fallback chain")

def primary_api():
    raise ConnectionError("Primary API down")

def backup_api():
    raise ConnectionError("Backup API down")

def cached_response():
    return {"data": "cached_value", "cached_at": "2024-01-01"}

chain: FallbackChain[dict] = FallbackChain()
chain.add("primary_api", primary_api)
chain.add("backup_api", backup_api)
chain.add("cached_response", cached_response)

result = chain.execute()
print(f"  Success: {result.success}")
print(f"  Used: {result.fallback_name} (fallback #{result.used_fallback})")
print(f"  Result: {result.result}")

# Test 2: Model fallback
print("\nTest 2: Model fallback chain")

model_call_count = 0

def mock_model_caller(model_id: str, prompt: str) -> str:
    global model_call_count
    model_call_count += 1
    if "opus" in model_id:
        raise Exception("Rate limited")
    if "sonnet" in model_id:
        raise Exception("Service unavailable")
    return f"Response from {model_id}: {prompt[:20]}..."

model_chain = ModelFallbackChain(mock_model_caller)
try:
    response, model_used, cost = model_chain.call("Explain quantum computing")
    print(f"  Model used: {model_used}")
    print(f"  Cost: ${cost}/1k tokens")
    print(f"  Response: {response}")
except RuntimeError as e:
    print(f"  All failed: {e}")

# Test 3: Graceful degradation
print("\nTest 3: Graceful degradation")

call_tier = 0

def full_response():
    global call_tier
    call_tier = 1
    raise Exception("Full service down")

def summary_response():
    global call_tier
    call_tier = 2
    raise Exception("Summary service down")

def cached():
    global call_tier
    call_tier = 3
    return "Cached: Last known good response from 1 hour ago"

degradation = GracefulDegradation(
    full_handler=full_response,
    summary_handler=summary_response,
    cache_handler=cached,
    error_message="Service unavailable. Please try again later."
)

response, tier = degradation.execute()
print(f"  Tier: {tier}")
print(f"  Response: {response}")

# Test 4: All fallbacks fail
print("\nTest 4: Complete failure with error message")

def always_fail():
    raise Exception("Service down")

degradation_fail = GracefulDegradation(
    full_handler=always_fail,
    summary_handler=always_fail,
    cache_handler=always_fail,
    error_message="All services are currently unavailable. Please try again in 5 minutes."
)

response, tier = degradation_fail.execute()
print(f"  Tier: {tier}")
print(f"  Response: {response}")

print("\n  Key insight: Fallback chains provide resilience")
print("  - Service fallbacks: primary -> backup -> cache")
print("  - Model fallbacks: expensive -> cheap (cost savings)")
print("  - Graceful degradation: full -> summary -> cached -> error")


# ============================================================================
# ITERATION 5: Circuit Breaker Pattern
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 5: Circuit Breaker Pattern")
print("=" * 70)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation, requests flow through
    OPEN = "open"          # Failing, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior.

    Attributes:
        failure_threshold: Number of failures before opening circuit
        success_threshold: Successes needed in half-open to close
        recovery_timeout: Seconds to wait before testing (half-open)
        failure_rate_threshold: Alternative: open if failure rate exceeds this
        window_size: Number of calls to track for rate calculation
    """
    failure_threshold: int = 5
    success_threshold: int = 2
    recovery_timeout: float = 30.0
    failure_rate_threshold: float = 0.5
    window_size: int = 10


@dataclass
class CircuitBreakerMetrics:
    """Metrics for circuit breaker monitoring."""
    state: CircuitState
    failure_count: int
    success_count: int
    total_calls: int
    last_failure_time: datetime | None
    last_state_change: datetime
    time_in_state: float


class CircuitBreaker:
    """Circuit breaker pattern for protecting services.

    States:
    - CLOSED: Normal operation. Failures are counted.
    - OPEN: Circuit is tripped. Calls fail immediately.
    - HALF_OPEN: Testing recovery. Limited calls allowed.

    Transitions:
    - CLOSED -> OPEN: When failure_threshold exceeded
    - OPEN -> HALF_OPEN: After recovery_timeout
    - HALF_OPEN -> CLOSED: When success_threshold met
    - HALF_OPEN -> OPEN: On any failure
    """

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.half_open_successes = 0
        self.last_failure_time: datetime | None = None
        self.last_state_change = datetime.now()
        self.call_history: list[tuple[datetime, bool]] = []  # (time, success)

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state with logging."""
        if self.state != new_state:
            print(f"  [Circuit:{self.name}] {self.state.value} -> {new_state.value}")
            self.state = new_state
            self.last_state_change = datetime.now()

            if new_state == CircuitState.HALF_OPEN:
                self.half_open_successes = 0
            elif new_state == CircuitState.CLOSED:
                self.failure_count = 0
                self.success_count = 0

    def _calculate_failure_rate(self) -> float:
        """Calculate recent failure rate."""
        if not self.call_history:
            return 0.0

        recent = self.call_history[-self.config.window_size:]
        if len(recent) < self.config.window_size // 2:
            return 0.0  # Not enough data

        failures = sum(1 for _, success in recent if not success)
        return failures / len(recent)

    def can_execute(self) -> tuple[bool, str]:
        """Check if execution is allowed.

        Returns:
            Tuple of (allowed, reason)
        """
        if self.state == CircuitState.CLOSED:
            return True, "Circuit closed"

        elif self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if self.last_failure_time:
                elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                if elapsed >= self.config.recovery_timeout:
                    self._transition_to(CircuitState.HALF_OPEN)
                    return True, "Testing recovery"
            return False, f"Circuit open (wait {self.config.recovery_timeout}s)"

        else:  # HALF_OPEN
            return True, "Half-open test"

    def record_success(self) -> None:
        """Record a successful call."""
        self.success_count += 1
        self.call_history.append((datetime.now(), True))

        # Trim history
        if len(self.call_history) > self.config.window_size * 2:
            self.call_history = self.call_history[-self.config.window_size:]

        if self.state == CircuitState.HALF_OPEN:
            self.half_open_successes += 1
            if self.half_open_successes >= self.config.success_threshold:
                self._transition_to(CircuitState.CLOSED)

    def record_failure(self) -> None:
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        self.call_history.append((datetime.now(), False))

        # Trim history
        if len(self.call_history) > self.config.window_size * 2:
            self.call_history = self.call_history[-self.config.window_size:]

        if self.state == CircuitState.HALF_OPEN:
            # Any failure in half-open immediately opens
            self._transition_to(CircuitState.OPEN)

        elif self.state == CircuitState.CLOSED:
            # Check thresholds
            if self.failure_count >= self.config.failure_threshold:
                self._transition_to(CircuitState.OPEN)
            elif self._calculate_failure_rate() >= self.config.failure_rate_threshold:
                self._transition_to(CircuitState.OPEN)

    def execute(self, func: Callable[[], T]) -> T:
        """Execute a function with circuit breaker protection.

        Raises:
            CircuitOpenError: If circuit is open
            Exception: If the function fails
        """
        allowed, reason = self.can_execute()

        if not allowed:
            raise CircuitOpenError(f"Circuit breaker '{self.name}' is open: {reason}")

        try:
            result = func()
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise

    def get_metrics(self) -> CircuitBreakerMetrics:
        """Get current circuit breaker metrics."""
        return CircuitBreakerMetrics(
            state=self.state,
            failure_count=self.failure_count,
            success_count=self.success_count,
            total_calls=len(self.call_history),
            last_failure_time=self.last_failure_time,
            last_state_change=self.last_state_change,
            time_in_state=(datetime.now() - self.last_state_change).total_seconds()
        )


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""

    def __init__(self):
        self.breakers: dict[str, CircuitBreaker] = {}

    def get_or_create(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None
    ) -> CircuitBreaker:
        """Get existing or create new circuit breaker."""
        if name not in self.breakers:
            self.breakers[name] = CircuitBreaker(name, config)
        return self.breakers[name]

    def get_all_metrics(self) -> dict[str, CircuitBreakerMetrics]:
        """Get metrics for all circuit breakers."""
        return {name: cb.get_metrics() for name, cb in self.breakers.items()}


# Demo Iteration 5
print("\nDemo: Circuit Breaker Pattern")
print("-" * 40)

# Create a circuit breaker with low thresholds for demo
config = CircuitBreakerConfig(
    failure_threshold=3,
    success_threshold=2,
    recovery_timeout=2.0  # Short for demo
)
breaker = CircuitBreaker("external_api", config)

call_count = 0

def flaky_service():
    global call_count
    call_count += 1
    if call_count <= 4:  # First 4 calls fail
        raise ConnectionError(f"Service unavailable (call {call_count})")
    return f"Success (call {call_count})"

print("\nTest: Circuit breaker state transitions")
print("-" * 50)

# Make calls until circuit opens
for i in range(10):
    metrics = breaker.get_metrics()
    print(f"\nCall {i+1} | State: {metrics.state.value} | Failures: {metrics.failure_count}")

    try:
        result = breaker.execute(flaky_service)
        print(f"  Result: {result}")
    except CircuitOpenError as e:
        print(f"  BLOCKED: {e}")
        # Wait for recovery timeout
        if i < 9:
            print(f"  Waiting {config.recovery_timeout}s for recovery...")
            time.sleep(config.recovery_timeout + 0.1)
    except ConnectionError as e:
        print(f"  FAILED: {e}")

# Final metrics
metrics = breaker.get_metrics()
print(f"\nFinal State: {metrics.state.value}")
print(f"Total Failures: {metrics.failure_count}")
print(f"Total Successes: {metrics.success_count}")

print("\n  Key insight: Circuit breaker prevents cascade failures")
print("  - CLOSED: Normal operation, count failures")
print("  - OPEN: Block calls, fail fast, prevent overload")
print("  - HALF_OPEN: Test recovery with limited calls")


# ============================================================================
# ITERATION 6: Checkpoint & Resume
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 6: Checkpoint & Resume")
print("=" * 70)


@dataclass
class Checkpoint:
    """A checkpoint representing workflow state at a point in time.

    Attributes:
        checkpoint_id: Unique identifier
        workflow_id: ID of the workflow this belongs to
        step_index: Index of the completed step
        step_name: Name of the completed step
        state: Serialized state at this point
        created_at: When checkpoint was created
        metadata: Additional context (errors, outputs, etc.)
    """
    checkpoint_id: str
    workflow_id: str
    step_index: int
    step_name: str
    state: dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize checkpoint to dictionary."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "workflow_id": self.workflow_id,
            "step_index": self.step_index,
            "step_name": self.step_name,
            "state": self.state,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Checkpoint":
        """Deserialize checkpoint from dictionary."""
        return cls(
            checkpoint_id=data["checkpoint_id"],
            workflow_id=data["workflow_id"],
            step_index=data["step_index"],
            step_name=data["step_name"],
            state=data["state"],
            created_at=datetime.fromisoformat(data["created_at"]),
            metadata=data.get("metadata", {})
        )


class CheckpointManager:
    """Manage workflow checkpoints for resume capability.

    Storage backends:
    - Memory (default): Fast, ephemeral
    - File: JSON files, persistent
    - (Future: S3, DynamoDB)
    """

    def __init__(self, storage_dir: str | None = None):
        self.storage_dir = storage_dir
        self.memory_store: dict[str, list[Checkpoint]] = {}

    def save(self, checkpoint: Checkpoint) -> None:
        """Save a checkpoint."""
        # Memory store
        if checkpoint.workflow_id not in self.memory_store:
            self.memory_store[checkpoint.workflow_id] = []
        self.memory_store[checkpoint.workflow_id].append(checkpoint)

        # File store (if configured)
        if self.storage_dir:
            import os
            os.makedirs(self.storage_dir, exist_ok=True)
            filepath = os.path.join(
                self.storage_dir,
                f"{checkpoint.workflow_id}_{checkpoint.step_index}.json"
            )
            with open(filepath, 'w') as f:
                json.dump(checkpoint.to_dict(), f, indent=2)

    def get_latest(self, workflow_id: str) -> Checkpoint | None:
        """Get the most recent checkpoint for a workflow."""
        checkpoints = self.memory_store.get(workflow_id, [])
        if not checkpoints:
            return None
        return max(checkpoints, key=lambda c: c.step_index)

    def get_all(self, workflow_id: str) -> list[Checkpoint]:
        """Get all checkpoints for a workflow."""
        return self.memory_store.get(workflow_id, [])

    def clear(self, workflow_id: str) -> None:
        """Clear all checkpoints for a workflow."""
        if workflow_id in self.memory_store:
            del self.memory_store[workflow_id]


@dataclass
class WorkflowStep:
    """A step in a resumable workflow."""
    name: str
    handler: Callable[[dict], dict]
    retryable: bool = True
    checkpoint: bool = True  # Whether to checkpoint after this step


class ResumableWorkflow:
    """A workflow that can be resumed from checkpoints.

    Features:
    - Automatic checkpointing after each step
    - Resume from last successful checkpoint
    - Step-level retry with exponential backoff
    """

    def __init__(
        self,
        workflow_id: str,
        steps: list[WorkflowStep],
        checkpoint_manager: CheckpointManager | None = None,
        retry_config: RetryConfig | None = None
    ):
        self.workflow_id = workflow_id
        self.steps = steps
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self.retry_config = retry_config or RetryConfig(max_retries=2, base_delay=0.5)
        self.retry_executor = RetryExecutor(self.retry_config)

    def execute(self, initial_state: dict | None = None, resume: bool = True) -> dict:
        """Execute the workflow, optionally resuming from checkpoint.

        Args:
            initial_state: Starting state (ignored if resuming)
            resume: Whether to resume from last checkpoint

        Returns:
            Final workflow state
        """
        state = initial_state or {}
        start_index = 0

        # Check for resume
        if resume:
            checkpoint = self.checkpoint_manager.get_latest(self.workflow_id)
            if checkpoint:
                print(f"  Resuming from checkpoint: step {checkpoint.step_index} ({checkpoint.step_name})")
                state = checkpoint.state
                start_index = checkpoint.step_index + 1

        # Execute steps
        for i, step in enumerate(self.steps[start_index:], start=start_index):
            print(f"  Executing step {i}: {step.name}")

            try:
                # Execute with retry if retryable
                if step.retryable:
                    result = self.retry_executor.execute(step.handler, state)
                    if not result.success:
                        raise result.error or Exception(f"Step {step.name} failed after retries")
                    state = result.result
                else:
                    state = step.handler(state)

                # Checkpoint after successful step
                if step.checkpoint:
                    checkpoint = Checkpoint(
                        checkpoint_id=str(uuid.uuid4())[:8],
                        workflow_id=self.workflow_id,
                        step_index=i,
                        step_name=step.name,
                        state=state.copy()
                    )
                    self.checkpoint_manager.save(checkpoint)
                    print(f"  Checkpoint saved: {checkpoint.checkpoint_id}")

            except Exception as e:
                print(f"  Step {step.name} failed: {e}")
                raise WorkflowError(
                    f"Workflow failed at step {i} ({step.name}): {e}",
                    step_index=i,
                    step_name=step.name,
                    state=state
                )

        return state


class WorkflowError(Exception):
    """Error during workflow execution."""

    def __init__(self, message: str, step_index: int, step_name: str, state: dict):
        super().__init__(message)
        self.step_index = step_index
        self.step_name = step_name
        self.state = state


# Demo Iteration 6
print("\nDemo: Checkpoint & Resume")
print("-" * 40)

# Create a workflow with steps that may fail
failure_step = -1  # Which step should fail (-1 = none)

def step_fetch_data(state: dict) -> dict:
    if failure_step == 0:
        raise ConnectionError("Failed to fetch data")
    state["data"] = {"items": [1, 2, 3, 4, 5]}
    return state

def step_process_data(state: dict) -> dict:
    if failure_step == 1:
        raise ValueError("Processing error")
    state["processed"] = [x * 2 for x in state["data"]["items"]]
    return state

def step_validate_data(state: dict) -> dict:
    if failure_step == 2:
        raise AssertionError("Validation failed")
    state["valid"] = all(x > 0 for x in state["processed"])
    return state

def step_save_results(state: dict) -> dict:
    if failure_step == 3:
        raise IOError("Failed to save")
    state["saved"] = True
    state["result_id"] = "result_123"
    return state

workflow_steps = [
    WorkflowStep("fetch_data", step_fetch_data),
    WorkflowStep("process_data", step_process_data),
    WorkflowStep("validate_data", step_validate_data),
    WorkflowStep("save_results", step_save_results),
]

checkpoint_mgr = CheckpointManager()

# Test 1: Complete workflow
print("\nTest 1: Complete workflow execution")
failure_step = -1
workflow = ResumableWorkflow("workflow_1", workflow_steps, checkpoint_mgr)
try:
    final_state = workflow.execute({})
    print(f"  Final state: {final_state}")
except WorkflowError as e:
    print(f"  Failed: {e}")

# Test 2: Workflow fails midway
print("\nTest 2: Workflow fails at step 2")
failure_step = 2
checkpoint_mgr.clear("workflow_2")
workflow = ResumableWorkflow(
    "workflow_2",
    workflow_steps,
    checkpoint_mgr,
    RetryConfig(max_retries=1, base_delay=0.1)
)
try:
    workflow.execute({})
except WorkflowError as e:
    print(f"  Failed at step {e.step_index}: {e.step_name}")
    print(f"  State at failure: {e.state}")

# Test 3: Resume from checkpoint
print("\nTest 3: Resume from last checkpoint")
failure_step = -1  # No more failures
workflow = ResumableWorkflow("workflow_2", workflow_steps, checkpoint_mgr)
try:
    final_state = workflow.execute({}, resume=True)
    print(f"  Resumed and completed!")
    print(f"  Final state: {final_state}")
except WorkflowError as e:
    print(f"  Failed: {e}")

# Show checkpoints
print("\nCheckpoints for workflow_2:")
for cp in checkpoint_mgr.get_all("workflow_2"):
    print(f"  - Step {cp.step_index}: {cp.step_name} @ {cp.created_at.strftime('%H:%M:%S')}")

print("\n  Key insight: Checkpointing enables reliable long-running workflows")
print("  - Save state after each step")
print("  - Resume from last checkpoint on failure")
print("  - Combine with retry for maximum resilience")


# ============================================================================
# ITERATION 7: Human Escalation
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 7: Human Escalation")
print("=" * 70)


class EscalationLevel(Enum):
    """Levels of escalation severity."""
    INFO = "info"           # FYI, no action needed
    WARNING = "warning"     # Attention needed soon
    CRITICAL = "critical"   # Immediate attention required
    EMERGENCY = "emergency" # Requires immediate human intervention


@dataclass
class EscalationTrigger:
    """Condition that triggers escalation.

    Attributes:
        name: Trigger identifier
        level: Escalation severity
        condition: Function(metrics) -> bool
        message_template: Template for escalation message
    """
    name: str
    level: EscalationLevel
    condition: Callable[[dict], bool]
    message_template: str


@dataclass
class EscalationEvent:
    """An escalation event that was triggered."""
    event_id: str
    trigger_name: str
    level: EscalationLevel
    message: str
    context: dict
    created_at: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None


class EscalationHandler(ABC):
    """Base class for escalation handlers."""

    @abstractmethod
    def send(self, event: EscalationEvent) -> bool:
        """Send an escalation notification."""
        pass


class LoggingEscalationHandler(EscalationHandler):
    """Log escalations (for development/testing)."""

    def send(self, event: EscalationEvent) -> bool:
        level_emoji = {
            EscalationLevel.INFO: "i",
            EscalationLevel.WARNING: "!",
            EscalationLevel.CRITICAL: "!!",
            EscalationLevel.EMERGENCY: "!!!"
        }
        emoji = level_emoji.get(event.level, "?")
        print(f"  [{emoji}] ESCALATION [{event.level.value.upper()}]: {event.message}")
        return True


class WebhookEscalationHandler(EscalationHandler):
    """Send escalations to a webhook (Slack, PagerDuty, etc.)."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, event: EscalationEvent) -> bool:
        # In production, would POST to webhook
        print(f"  [Webhook] Would POST to {self.webhook_url}")
        print(f"  [Webhook] Event: {event.level.value} - {event.message}")
        return True


class EscalationPolicy:
    """Policy for when and how to escalate.

    Checks various conditions and triggers appropriate escalations.
    """

    def __init__(
        self,
        triggers: list[EscalationTrigger] | None = None,
        handlers: list[EscalationHandler] | None = None
    ):
        self.triggers = triggers or self._default_triggers()
        self.handlers = handlers or [LoggingEscalationHandler()]
        self.events: list[EscalationEvent] = []

    def _default_triggers(self) -> list[EscalationTrigger]:
        """Default escalation triggers."""
        return [
            EscalationTrigger(
                name="high_failure_rate",
                level=EscalationLevel.WARNING,
                condition=lambda m: m.get("failure_rate", 0) > 0.5,
                message_template="High failure rate: {failure_rate:.1%}"
            ),
            EscalationTrigger(
                name="circuit_open",
                level=EscalationLevel.CRITICAL,
                condition=lambda m: m.get("circuit_state") == "open",
                message_template="Circuit breaker open for {service_name}"
            ),
            EscalationTrigger(
                name="retries_exhausted",
                level=EscalationLevel.WARNING,
                condition=lambda m: m.get("retries_exhausted", False),
                message_template="All retries exhausted for {operation_name}"
            ),
            EscalationTrigger(
                name="cost_threshold",
                level=EscalationLevel.CRITICAL,
                condition=lambda m: m.get("cost_spent", 0) > m.get("cost_limit", float('inf')) * 0.9,
                message_template="Cost threshold reached: ${cost_spent:.2f} / ${cost_limit:.2f}"
            ),
            EscalationTrigger(
                name="data_loss_risk",
                level=EscalationLevel.EMERGENCY,
                condition=lambda m: m.get("data_loss_risk", False),
                message_template="EMERGENCY: Potential data loss in {component}"
            ),
        ]

    def check(self, metrics: dict) -> list[EscalationEvent]:
        """Check metrics against triggers and create events."""
        events = []

        for trigger in self.triggers:
            if trigger.condition(metrics):
                message = trigger.message_template.format(**metrics)
                event = EscalationEvent(
                    event_id=str(uuid.uuid4())[:8],
                    trigger_name=trigger.name,
                    level=trigger.level,
                    message=message,
                    context=metrics.copy()
                )
                events.append(event)
                self.events.append(event)

                # Send to handlers
                for handler in self.handlers:
                    handler.send(event)

        return events


class HumanInTheLoop:
    """Pause execution and wait for human decision.

    In production, this would:
    1. Send notification to human
    2. Poll for response (or webhook callback)
    3. Return human decision

    For demo, simulates with timeout or mock response.
    """

    def __init__(
        self,
        escalation_policy: EscalationPolicy | None = None,
        timeout_seconds: float = 300.0,
        default_action: str = "abort"
    ):
        self.escalation_policy = escalation_policy or EscalationPolicy()
        self.timeout_seconds = timeout_seconds
        self.default_action = default_action
        self.pending_decisions: dict[str, dict] = {}

    def request_decision(
        self,
        question: str,
        options: list[str],
        context: dict,
        level: EscalationLevel = EscalationLevel.CRITICAL
    ) -> tuple[str, str]:
        """Request a decision from a human.

        Args:
            question: The decision to be made
            options: Available choices
            context: Relevant context for decision
            level: Escalation level

        Returns:
            Tuple of (decision, decision_source)
        """
        decision_id = str(uuid.uuid4())[:8]

        # Create escalation event
        event = EscalationEvent(
            event_id=decision_id,
            trigger_name="human_decision_required",
            level=level,
            message=f"Decision required: {question}",
            context={**context, "options": options}
        )

        # Send to handlers
        for handler in self.escalation_policy.handlers:
            handler.send(event)

        print(f"  [HumanInTheLoop] Decision ID: {decision_id}")
        print(f"  [HumanInTheLoop] Question: {question}")
        print(f"  [HumanInTheLoop] Options: {options}")

        # In production, would wait for callback
        # For demo, simulate with mock response
        mock_decision = self._simulate_human_response(options)

        return mock_decision, "simulated"

    def _simulate_human_response(self, options: list[str]) -> str:
        """Simulate human response for demo."""
        # Simulate some thinking time
        time.sleep(0.5)
        # Return first option as mock response
        return options[0] if options else self.default_action


# Demo Iteration 7
print("\nDemo: Human Escalation")
print("-" * 40)

# Create escalation policy with handlers
policy = EscalationPolicy(handlers=[
    LoggingEscalationHandler(),
    WebhookEscalationHandler("https://hooks.slack.com/services/xxx")
])

# Test 1: Automatic escalation based on metrics
print("\nTest 1: Metric-based escalation triggers")
metrics = {
    "failure_rate": 0.75,
    "service_name": "payment_api",
    "operation_name": "process_payment",
    "retries_exhausted": True,
    "cost_spent": 95.0,
    "cost_limit": 100.0
}

events = policy.check(metrics)
print(f"\n  Triggered {len(events)} escalation(s)")

# Test 2: Human in the loop decision
print("\nTest 2: Human-in-the-loop decision")
hitl = HumanInTheLoop(policy)

decision, source = hitl.request_decision(
    question="Payment processing failed 5 times. How to proceed?",
    options=["retry_with_manual_review", "refund_customer", "abort_and_notify"],
    context={
        "transaction_id": "txn_12345",
        "amount": 150.00,
        "customer_id": "cust_789",
        "error": "Card declined"
    },
    level=EscalationLevel.CRITICAL
)

print(f"\n  Decision: {decision}")
print(f"  Source: {source}")

# Test 3: Emergency escalation
print("\nTest 3: Emergency escalation")
emergency_metrics = {
    "data_loss_risk": True,
    "component": "database_replication"
}
events = policy.check(emergency_metrics)

print("\n  Key insight: Human escalation is the safety net")
print("  - Automatic triggers based on metrics")
print("  - Multiple notification channels (log, webhook, SMS)")
print("  - Human-in-the-loop for critical decisions")
print("  - Audit trail of all escalations")


# ============================================================================
# ITERATION 8: AWS SQS Dead-Letter Queues
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 8: AWS SQS Dead-Letter Queues")
print("=" * 70)


@dataclass
class SQSMessage:
    """Simulated SQS message."""
    message_id: str
    body: dict
    receipt_handle: str
    approximate_receive_count: int = 1
    sent_timestamp: datetime = field(default_factory=datetime.now)
    attributes: dict = field(default_factory=dict)


class MockSQSQueue:
    """Mock SQS queue for local development/testing."""

    def __init__(self, queue_name: str, visibility_timeout: int = 30):
        self.queue_name = queue_name
        self.visibility_timeout = visibility_timeout
        self.messages: list[SQSMessage] = []
        self.in_flight: dict[str, tuple[SQSMessage, datetime]] = {}

    def send_message(self, body: dict) -> SQSMessage:
        """Send a message to the queue."""
        msg = SQSMessage(
            message_id=str(uuid.uuid4())[:8],
            body=body,
            receipt_handle=str(uuid.uuid4())
        )
        self.messages.append(msg)
        return msg

    def receive_message(self) -> SQSMessage | None:
        """Receive a message from the queue."""
        # Return messages from in-flight if visibility expired
        now = datetime.now()
        for handle, (msg, invisible_until) in list(self.in_flight.items()):
            if now > invisible_until:
                del self.in_flight[handle]
                msg.approximate_receive_count += 1
                msg.receipt_handle = str(uuid.uuid4())
                self.messages.append(msg)

        if not self.messages:
            return None

        msg = self.messages.pop(0)
        invisible_until = now + timedelta(seconds=self.visibility_timeout)
        self.in_flight[msg.receipt_handle] = (msg, invisible_until)
        return msg

    def delete_message(self, receipt_handle: str) -> bool:
        """Delete a message (acknowledge successful processing)."""
        if receipt_handle in self.in_flight:
            del self.in_flight[receipt_handle]
            return True
        return False

    def get_queue_length(self) -> int:
        """Get approximate number of messages."""
        return len(self.messages) + len(self.in_flight)


class DLQHandler:
    """Handle messages that failed processing and went to DLQ."""

    def __init__(
        self,
        main_queue: MockSQSQueue,
        dlq: MockSQSQueue,
        max_receive_count: int = 3
    ):
        self.main_queue = main_queue
        self.dlq = dlq
        self.max_receive_count = max_receive_count

    def process_message(
        self,
        msg: SQSMessage,
        handler: Callable[[dict], bool]
    ) -> tuple[bool, str]:
        """Process a message with DLQ handling.

        Args:
            msg: The message to process
            handler: Function(body) -> success

        Returns:
            Tuple of (success, disposition)
        """
        try:
            success = handler(msg.body)

            if success:
                self.main_queue.delete_message(msg.receipt_handle)
                return True, "processed"
            else:
                # Processing returned False - treat as failure
                return self._handle_failure(msg, "Handler returned False")

        except Exception as e:
            return self._handle_failure(msg, str(e))

    def _handle_failure(
        self,
        msg: SQSMessage,
        error: str
    ) -> tuple[bool, str]:
        """Handle a processing failure."""
        if msg.approximate_receive_count >= self.max_receive_count:
            # Move to DLQ
            msg.attributes["dlq_reason"] = error
            msg.attributes["original_queue"] = self.main_queue.queue_name
            self.dlq.send_message({
                "original_body": msg.body,
                "error": error,
                "receive_count": msg.approximate_receive_count
            })
            self.main_queue.delete_message(msg.receipt_handle)
            return False, "moved_to_dlq"
        else:
            # Let visibility timeout expire for retry
            return False, "will_retry"


class DLQRecoveryManager:
    """Manage recovery of messages from DLQ."""

    def __init__(self, dlq: MockSQSQueue, main_queue: MockSQSQueue):
        self.dlq = dlq
        self.main_queue = main_queue
        self.recovered_count = 0
        self.failed_count = 0

    def replay_all(
        self,
        transform: Callable[[dict], dict] | None = None,
        filter_fn: Callable[[dict], bool] | None = None
    ) -> tuple[int, int]:
        """Replay all messages from DLQ back to main queue.

        Args:
            transform: Optional transformation before replay
            filter_fn: Optional filter (True = replay)

        Returns:
            Tuple of (replayed_count, skipped_count)
        """
        replayed = 0
        skipped = 0

        while True:
            msg = self.dlq.receive_message()
            if not msg:
                break

            body = msg.body.get("original_body", msg.body)

            # Apply filter
            if filter_fn and not filter_fn(body):
                skipped += 1
                self.dlq.delete_message(msg.receipt_handle)
                continue

            # Apply transformation
            if transform:
                body = transform(body)

            # Replay to main queue
            self.main_queue.send_message(body)
            self.dlq.delete_message(msg.receipt_handle)
            replayed += 1

        self.recovered_count += replayed
        return replayed, skipped


# Demo Iteration 8
print("\nDemo: SQS Dead-Letter Queues")
print("-" * 40)

# Create queues
main_queue = MockSQSQueue("order-processing", visibility_timeout=5)
dlq = MockSQSQueue("order-processing-dlq")
dlq_handler = DLQHandler(main_queue, dlq, max_receive_count=3)

# Simulate message processing with failures
process_count = 0

def process_order(body: dict) -> bool:
    global process_count
    process_count += 1
    order_id = body.get("order_id")

    # Simulate: orders 2 and 3 always fail
    if order_id in [2, 3]:
        raise ValueError(f"Cannot process order {order_id}")
    return True

# Send some orders
print("\nTest 1: Send and process orders")
for i in range(1, 6):
    main_queue.send_message({"order_id": i, "amount": i * 10.0})

print(f"  Queue length: {main_queue.get_queue_length()}")

# Process messages (multiple rounds to trigger DLQ)
for round_num in range(4):
    print(f"\n  Round {round_num + 1}:")
    while True:
        msg = main_queue.receive_message()
        if not msg:
            break

        success, disposition = dlq_handler.process_message(msg, process_order)
        order_id = msg.body.get("order_id")
        print(f"    Order {order_id}: {disposition} (receive #{msg.approximate_receive_count})")

    # Small delay to let visibility timeout expire
    time.sleep(0.1)

print(f"\n  Main queue: {main_queue.get_queue_length()} messages")
print(f"  DLQ: {dlq.get_queue_length()} messages")

# Test 2: Recover from DLQ
print("\nTest 2: Recover messages from DLQ")
recovery = DLQRecoveryManager(dlq, main_queue)

# Fix the issue and replay
def fix_order(body: dict) -> dict:
    """Transform to fix the problematic orders."""
    body["fixed"] = True
    return body

replayed, skipped = recovery.replay_all(transform=fix_order)
print(f"  Replayed: {replayed}, Skipped: {skipped}")
print(f"  Main queue now: {main_queue.get_queue_length()} messages")

print("\n  Key insight: DLQ is the safety net for message processing")
print("  - Failed messages don't get lost")
print("  - Configurable retry count before DLQ")
print("  - Recovery manager for bulk replay")
print("  - Transform messages during recovery to fix issues")


# ============================================================================
# ITERATION 9: AWS Step Functions Retry
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 9: AWS Step Functions Retry")
print("=" * 70)


@dataclass
class StepFunctionRetryConfig:
    """Step Functions-style retry configuration.

    Mirrors AWS Step Functions retry semantics:
    - ErrorEquals: Errors to retry on
    - IntervalSeconds: Initial retry interval
    - MaxAttempts: Maximum retry count
    - BackoffRate: Multiplier for exponential backoff
    - MaxDelaySeconds: Maximum delay cap
    """
    error_equals: list[str]
    interval_seconds: float = 1.0
    max_attempts: int = 3
    backoff_rate: float = 2.0
    max_delay_seconds: float = 60.0

    def matches_error(self, error: Exception) -> bool:
        """Check if error matches this retry config."""
        error_name = type(error).__name__
        error_msg = str(error).lower()

        for pattern in self.error_equals:
            if pattern == "States.ALL":
                return True
            if pattern == "States.Timeout" and "timeout" in error_msg:
                return True
            if pattern == "States.TaskFailed":
                return True
            if pattern == error_name:
                return True
            if pattern.lower() in error_msg:
                return True
        return False

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt."""
        delay = self.interval_seconds * (self.backoff_rate ** attempt)
        return min(delay, self.max_delay_seconds)


@dataclass
class StepFunctionCatchConfig:
    """Step Functions-style catch configuration.

    Specifies how to handle errors that aren't retried.
    """
    error_equals: list[str]
    next_state: str
    result_path: str = "$.error"


class StepFunctionState(ABC):
    """Base class for Step Function states."""

    def __init__(
        self,
        name: str,
        retry: list[StepFunctionRetryConfig] | None = None,
        catch: list[StepFunctionCatchConfig] | None = None
    ):
        self.name = name
        self.retry = retry or []
        self.catch = catch or []

    @abstractmethod
    def execute(self, input_data: dict) -> dict:
        """Execute this state."""
        pass

    def get_retry_config(self, error: Exception) -> StepFunctionRetryConfig | None:
        """Find matching retry config for an error."""
        for config in self.retry:
            if config.matches_error(error):
                return config
        return None

    def get_catch_config(self, error: Exception) -> StepFunctionCatchConfig | None:
        """Find matching catch config for an error."""
        for config in self.catch:
            if any(
                pattern == "States.ALL" or
                pattern == type(error).__name__
                for pattern in config.error_equals
            ):
                return config
        return None


class TaskState(StepFunctionState):
    """A Task state that executes a handler function."""

    def __init__(
        self,
        name: str,
        handler: Callable[[dict], dict],
        retry: list[StepFunctionRetryConfig] | None = None,
        catch: list[StepFunctionCatchConfig] | None = None
    ):
        super().__init__(name, retry, catch)
        self.handler = handler

    def execute(self, input_data: dict) -> dict:
        """Execute the task handler."""
        return self.handler(input_data)


class StepFunctionExecutor:
    """Execute Step Function-style state machines with retry/catch.

    Implements AWS Step Functions retry semantics locally.
    """

    def __init__(self, states: dict[str, StepFunctionState]):
        self.states = states
        self.execution_history: list[dict] = []

    def execute(
        self,
        start_state: str,
        input_data: dict,
        end_states: set[str] | None = None
    ) -> tuple[dict, str]:
        """Execute the state machine.

        Args:
            start_state: Name of starting state
            input_data: Input data for execution
            end_states: States that end execution (default: any missing next)

        Returns:
            Tuple of (output_data, final_state)
        """
        end_states = end_states or set()
        current_state = start_state
        data = input_data.copy()

        while current_state:
            state = self.states.get(current_state)
            if not state:
                raise ValueError(f"Unknown state: {current_state}")

            print(f"  [State: {current_state}]")

            # Execute with retry logic
            result, next_state, error = self._execute_with_retry(state, data)

            self.execution_history.append({
                "state": current_state,
                "input": data,
                "output": result,
                "error": str(error) if error else None,
                "next": next_state
            })

            if result is not None:
                data = result

            if current_state in end_states or not next_state:
                return data, current_state

            current_state = next_state

        return data, current_state

    def _execute_with_retry(
        self,
        state: StepFunctionState,
        data: dict
    ) -> tuple[dict | None, str | None, Exception | None]:
        """Execute state with Step Functions retry semantics."""
        retry_counts: dict[str, int] = {}  # Track retries per config

        while True:
            try:
                result = state.execute(data)
                # Determine next state (simplified - would use state.next in real impl)
                return result, None, None

            except Exception as e:
                print(f"    Error: {type(e).__name__}: {e}")

                # Find matching retry config
                retry_config = state.get_retry_config(e)

                if retry_config:
                    # Track attempts for this config
                    config_key = str(retry_config.error_equals)
                    retry_counts[config_key] = retry_counts.get(config_key, 0) + 1
                    attempt = retry_counts[config_key]

                    if attempt <= retry_config.max_attempts:
                        delay = retry_config.get_delay(attempt - 1)
                        print(f"    Retry {attempt}/{retry_config.max_attempts} in {delay:.1f}s")
                        time.sleep(delay)
                        continue

                # No more retries - try catch
                catch_config = state.get_catch_config(e)

                if catch_config:
                    error_output = {
                        "error": type(e).__name__,
                        "cause": str(e)
                    }
                    # Would update data at result_path
                    data["error"] = error_output
                    print(f"    Caught -> {catch_config.next_state}")
                    return data, catch_config.next_state, e

                # No catch - propagate error
                raise


# Demo Iteration 9
print("\nDemo: Step Functions Retry Patterns")
print("-" * 40)

# Create states with retry/catch configurations
task_call_count = 0

def process_payment(data: dict) -> dict:
    global task_call_count
    task_call_count += 1

    # Simulate failures
    if task_call_count <= 2:
        raise ConnectionError("Payment gateway timeout")

    data["payment_status"] = "completed"
    data["transaction_id"] = f"txn_{uuid.uuid4().hex[:8]}"
    return data

def handle_payment_failure(data: dict) -> dict:
    data["payment_status"] = "failed"
    data["refund_initiated"] = True
    return data

# Define states with Step Functions-style retry
payment_state = TaskState(
    name="ProcessPayment",
    handler=process_payment,
    retry=[
        StepFunctionRetryConfig(
            error_equals=["ConnectionError", "States.Timeout"],
            interval_seconds=0.5,
            max_attempts=3,
            backoff_rate=2.0
        )
    ],
    catch=[
        StepFunctionCatchConfig(
            error_equals=["States.ALL"],
            next_state="HandleFailure"
        )
    ]
)

failure_state = TaskState(
    name="HandleFailure",
    handler=handle_payment_failure
)

# Execute
print("\nTest 1: Retry succeeds")
task_call_count = 0
executor = StepFunctionExecutor({
    "ProcessPayment": payment_state,
    "HandleFailure": failure_state
})

result, final_state = executor.execute(
    "ProcessPayment",
    {"order_id": "ord_123", "amount": 99.99}
)

print(f"\n  Final state: {final_state}")
print(f"  Result: {result}")

# Test 2: Retry exhausted, caught
print("\nTest 2: Retry exhausted, caught by error handler")
task_call_count = 0

def always_fail(data: dict) -> dict:
    raise ConnectionError("Persistent failure")

persistent_failure_state = TaskState(
    name="AlwaysFails",
    handler=always_fail,
    retry=[
        StepFunctionRetryConfig(
            error_equals=["ConnectionError"],
            interval_seconds=0.2,
            max_attempts=2,
            backoff_rate=1.5
        )
    ],
    catch=[
        StepFunctionCatchConfig(
            error_equals=["States.ALL"],
            next_state="HandleFailure"
        )
    ]
)

executor2 = StepFunctionExecutor({
    "AlwaysFails": persistent_failure_state,
    "HandleFailure": failure_state
})

result, final_state = executor2.execute(
    "AlwaysFails",
    {"order_id": "ord_456", "amount": 50.00}
)

print(f"\n  Final state: {final_state}")
print(f"  Result: {result}")

# Show retry config patterns
print("\nCommon Step Functions Retry Patterns:")
print("-" * 50)

patterns = [
    ("API Gateway", StepFunctionRetryConfig(
        error_equals=["States.Timeout", "Lambda.ServiceException"],
        interval_seconds=1,
        max_attempts=3,
        backoff_rate=2.0
    )),
    ("Database", StepFunctionRetryConfig(
        error_equals=["DBConnectionError", "ThrottlingException"],
        interval_seconds=2,
        max_attempts=5,
        backoff_rate=1.5,
        max_delay_seconds=30
    )),
    ("Catch-All", StepFunctionRetryConfig(
        error_equals=["States.ALL"],
        interval_seconds=1,
        max_attempts=2,
        backoff_rate=2.0
    )),
]

for name, config in patterns:
    print(f"  {name}:")
    print(f"    Errors: {config.error_equals}")
    print(f"    Max attempts: {config.max_attempts}, Backoff: {config.backoff_rate}x")

print("\n  Key insight: Step Functions retry patterns are declarative")
print("  - ErrorEquals: Pattern matching on error types")
print("  - Configurable backoff rate and max delay")
print("  - Catch blocks for graceful error handling")
print("  - Composable with state machine flows")


# ============================================================================
# ITERATION 10: Unified RecoveryStack
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 10: Unified RecoveryStack")
print("=" * 70)


class RecoveryConfig(BaseModel):
    """Unified configuration for all recovery components."""

    # Retry settings
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: float = 0.1

    # Circuit breaker settings
    circuit_failure_threshold: int = 5
    circuit_success_threshold: int = 2
    circuit_recovery_timeout: float = 30.0

    # Fallback settings
    enable_model_fallback: bool = True
    fallback_models: list[str] = ["claude-sonnet-4", "claude-3-5-haiku", "gemini-2.0-flash"]

    # Escalation settings
    enable_escalation: bool = True
    escalation_failure_threshold: int = 3
    escalation_cost_threshold: float = 100.0

    # Checkpoint settings
    enable_checkpointing: bool = True
    checkpoint_storage_dir: str | None = None

    model_config = {"extra": "allow"}


@dataclass
class RecoveryMetrics:
    """Aggregated metrics from recovery operations."""
    total_attempts: int = 0
    successful_attempts: int = 0
    failed_attempts: int = 0
    retries_used: int = 0
    fallbacks_used: int = 0
    circuit_trips: int = 0
    escalations: int = 0
    checkpoints_created: int = 0
    total_delay_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_attempts == 0:
            return 1.0
        return self.successful_attempts / self.total_attempts


class RecoveryStack:
    """Unified recovery stack combining all error recovery patterns.

    Components:
    - Retry executor with exponential backoff
    - Failure classifier for smart retry decisions
    - Circuit breaker for service protection
    - Fallback chains for graceful degradation
    - Checkpoint manager for workflow resume
    - Escalation policy for human intervention

    Example:
        >>> config = RecoveryConfig(max_retries=3)
        >>> stack = RecoveryStack(config)
        >>> result = stack.execute("api_call", my_function, arg1, arg2)
    """

    def __init__(self, config: RecoveryConfig | None = None):
        self.config = config or RecoveryConfig()

        # Initialize components
        self.retry_config = RetryConfig(
            max_retries=self.config.max_retries,
            base_delay=self.config.base_delay,
            max_delay=self.config.max_delay,
            jitter=self.config.jitter
        )

        self.classifier = FailureClassifier()

        self.policy = TransientOnlyPolicy()  # Default: only retry transient

        self.circuit_breakers: dict[str, CircuitBreaker] = {}

        self.checkpoint_manager = CheckpointManager(
            self.config.checkpoint_storage_dir
        ) if self.config.enable_checkpointing else None

        self.escalation_policy = EscalationPolicy() if self.config.enable_escalation else None

        self.metrics = RecoveryMetrics()

    def get_circuit_breaker(self, service_name: str) -> CircuitBreaker:
        """Get or create circuit breaker for a service."""
        if service_name not in self.circuit_breakers:
            cb_config = CircuitBreakerConfig(
                failure_threshold=self.config.circuit_failure_threshold,
                success_threshold=self.config.circuit_success_threshold,
                recovery_timeout=self.config.circuit_recovery_timeout
            )
            self.circuit_breakers[service_name] = CircuitBreaker(service_name, cb_config)
        return self.circuit_breakers[service_name]

    def execute(
        self,
        operation_name: str,
        func: Callable,
        *args,
        service_name: str | None = None,
        fallback: Callable | None = None,
        **kwargs
    ) -> Any:
        """Execute an operation with full recovery stack.

        Args:
            operation_name: Name for logging/metrics
            func: Function to execute
            *args: Positional arguments
            service_name: Service name for circuit breaker (optional)
            fallback: Fallback function if all retries fail (optional)
            **kwargs: Keyword arguments

        Returns:
            Result of func or fallback

        Raises:
            Exception: If all recovery attempts fail and no fallback
        """
        self.metrics.total_attempts += 1

        # Check circuit breaker first
        if service_name:
            breaker = self.get_circuit_breaker(service_name)
            allowed, reason = breaker.can_execute()
            if not allowed:
                self.metrics.failed_attempts += 1
                self.metrics.circuit_trips += 1

                if fallback:
                    self.metrics.fallbacks_used += 1
                    return fallback(*args, **kwargs)

                raise CircuitOpenError(f"Circuit open for {service_name}: {reason}")

        # Execute with retry
        last_error: Exception | None = None

        for attempt in range(self.config.max_retries + 1):
            try:
                result = func(*args, **kwargs)

                # Record success
                self.metrics.successful_attempts += 1
                if attempt > 0:
                    self.metrics.retries_used += attempt

                if service_name:
                    self.get_circuit_breaker(service_name).record_success()

                return result

            except Exception as e:
                last_error = e

                # Classify failure
                failure = self.classifier.classify(e)

                # Record in circuit breaker
                if service_name:
                    self.get_circuit_breaker(service_name).record_failure()

                # Check if we should retry
                should_retry, delay = self.policy.should_retry(
                    failure, attempt + 1, self.config.max_retries + 1
                )

                if should_retry and attempt < self.config.max_retries:
                    delay = delay or self.retry_config.calculate_delay(attempt)
                    self.metrics.total_delay_seconds += delay
                    print(f"  [{operation_name}] Retry {attempt + 1}: {failure.failure_type.value}")
                    time.sleep(delay)
                else:
                    break

        # All retries exhausted
        self.metrics.failed_attempts += 1

        # Check escalation
        if self.escalation_policy:
            self.escalation_policy.check({
                "operation_name": operation_name,
                "failure_rate": 1 - self.metrics.success_rate,
                "retries_exhausted": True,
                "error": str(last_error)
            })
            self.metrics.escalations += 1

        # Try fallback
        if fallback:
            self.metrics.fallbacks_used += 1
            try:
                return fallback(*args, **kwargs)
            except Exception:
                pass  # Fallback also failed

        # Propagate error
        raise last_error  # type: ignore

    def get_metrics(self) -> RecoveryMetrics:
        """Get current recovery metrics."""
        return self.metrics

    def get_status(self) -> dict:
        """Get status of all recovery components."""
        return {
            "metrics": {
                "success_rate": f"{self.metrics.success_rate:.1%}",
                "total_attempts": self.metrics.total_attempts,
                "retries_used": self.metrics.retries_used,
                "fallbacks_used": self.metrics.fallbacks_used,
                "escalations": self.metrics.escalations
            },
            "circuit_breakers": {
                name: {
                    "state": cb.state.value,
                    "failures": cb.failure_count
                }
                for name, cb in self.circuit_breakers.items()
            },
            "config": {
                "max_retries": self.config.max_retries,
                "circuit_threshold": self.config.circuit_failure_threshold,
                "escalation_enabled": self.config.enable_escalation
            }
        }


class ResilientAgent:
    """Wrapper that adds recovery capabilities to any Strands Agent.

    Provides:
    - Automatic retry on transient failures
    - Circuit breaker protection
    - Model fallback on rate limits
    - Human escalation on critical failures
    """

    def __init__(
        self,
        agent_factory: Callable[[str], Any],  # model_id -> Agent
        recovery_stack: RecoveryStack | None = None,
        primary_model: str = "claude-sonnet-4"
    ):
        self.agent_factory = agent_factory
        self.recovery_stack = recovery_stack or RecoveryStack()
        self.primary_model = primary_model
        self.current_model = primary_model

    def __call__(self, prompt: str, **kwargs) -> str:
        """Execute prompt with full recovery."""

        def execute_with_model(model_id: str) -> str:
            agent = self.agent_factory(model_id)
            return str(agent(prompt, **kwargs))

        # Try primary model first
        try:
            return self.recovery_stack.execute(
                operation_name=f"agent_call_{self.primary_model}",
                func=execute_with_model,
                service_name="llm_api",
                fallback=lambda: self._fallback_execution(prompt, **kwargs),
                model_id=self.primary_model
            )
        except CircuitOpenError:
            # Circuit open - try fallback immediately
            return self._fallback_execution(prompt, **kwargs)

    def _fallback_execution(self, prompt: str, **kwargs) -> str:
        """Execute with fallback models."""
        fallback_models = self.recovery_stack.config.fallback_models

        for model_id in fallback_models:
            if model_id == self.primary_model:
                continue
            try:
                agent = self.agent_factory(model_id)
                result = str(agent(prompt, **kwargs))
                self.current_model = model_id
                return result
            except Exception:
                continue

        raise RuntimeError("All models failed")


# Demo Iteration 10
print("\nDemo: Unified RecoveryStack")
print("-" * 40)

# Create recovery stack with custom config
config = RecoveryConfig(
    max_retries=3,
    base_delay=0.2,
    circuit_failure_threshold=3,
    circuit_recovery_timeout=5.0,
    enable_escalation=True
)

stack = RecoveryStack(config)

# Simulate various operations
api_call_count = 0

def flaky_api(data: dict) -> dict:
    global api_call_count
    api_call_count += 1
    if api_call_count <= 2:
        raise ConnectionError("API unavailable")
    return {"status": "success", "data": data}

def cached_response(data: dict) -> dict:
    return {"status": "cached", "data": data, "stale": True}

print("\nTest 1: Successful recovery with retries")
api_call_count = 0
result = stack.execute(
    "get_user_data",
    flaky_api,
    service_name="user_api",
    fallback=cached_response,
    data={"user_id": 123}
)
print(f"  Result: {result}")

print("\nTest 2: Fallback used when retries exhausted")
api_call_count = 0

def always_fail(data: dict) -> dict:
    raise ConnectionError("Persistent failure")

result = stack.execute(
    "get_user_data",
    always_fail,
    service_name="broken_api",
    fallback=cached_response,
    data={"user_id": 456}
)
print(f"  Result: {result}")

print("\nTest 3: Circuit breaker trips after repeated failures")
for i in range(5):
    try:
        stack.execute(
            f"request_{i}",
            always_fail,
            service_name="unstable_api",
            data={}
        )
    except Exception as e:
        error_type = type(e).__name__
        print(f"  Request {i}: {error_type}")

# Show final status
print("\nRecovery Stack Status:")
print("-" * 40)
status = stack.get_status()

print("\nMetrics:")
for key, value in status["metrics"].items():
    print(f"  {key}: {value}")

print("\nCircuit Breakers:")
for name, cb_status in status["circuit_breakers"].items():
    print(f"  {name}: {cb_status['state']} (failures: {cb_status['failures']})")

print("\nConfiguration:")
for key, value in status["config"].items():
    print(f"  {key}: {value}")

# ============================================================================
# ITERATION 11: Fixed SQS DLQ Demo
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 11: Fixed SQS DLQ Demo")
print("=" * 70)


class FixedMockSQSQueue:
    """Fixed mock SQS queue with proper visibility timeout handling."""

    def __init__(self, queue_name: str, visibility_timeout: int = 30):
        self.queue_name = queue_name
        self.visibility_timeout = visibility_timeout
        self.messages: list[SQSMessage] = []
        self.in_flight: dict[str, tuple[SQSMessage, float]] = {}  # receipt -> (msg, invisible_until_timestamp)

    def send_message(self, body: dict) -> SQSMessage:
        """Send a message to the queue."""
        msg = SQSMessage(
            message_id=str(uuid.uuid4())[:8],
            body=body,
            receipt_handle=str(uuid.uuid4()),
            approximate_receive_count=0  # Start at 0, increment on receive
        )
        self.messages.append(msg)
        return msg

    def receive_message(self) -> SQSMessage | None:
        """Receive a message from the queue."""
        now = time.time()

        # Return messages from in-flight if visibility expired
        for handle, (msg, invisible_until) in list(self.in_flight.items()):
            if now > invisible_until:
                del self.in_flight[handle]
                # Message becomes visible again with new receipt handle
                msg.receipt_handle = str(uuid.uuid4())
                self.messages.append(msg)

        if not self.messages:
            return None

        msg = self.messages.pop(0)
        msg.approximate_receive_count += 1  # Increment on each receive
        invisible_until = now + self.visibility_timeout
        self.in_flight[msg.receipt_handle] = (msg, invisible_until)
        return msg

    def delete_message(self, receipt_handle: str) -> bool:
        """Delete a message (acknowledge successful processing)."""
        if receipt_handle in self.in_flight:
            del self.in_flight[receipt_handle]
            return True
        return False

    def get_queue_length(self) -> int:
        """Get approximate number of messages."""
        return len(self.messages) + len(self.in_flight)

    def make_visible_now(self, receipt_handle: str) -> None:
        """Force a message to become visible immediately (for testing)."""
        if receipt_handle in self.in_flight:
            msg, _ = self.in_flight[receipt_handle]
            del self.in_flight[receipt_handle]
            msg.receipt_handle = str(uuid.uuid4())
            self.messages.append(msg)


class FixedDLQHandler:
    """Fixed DLQ handler that properly moves messages after max receives."""

    def __init__(
        self,
        main_queue: FixedMockSQSQueue,
        dlq: FixedMockSQSQueue,
        max_receive_count: int = 3
    ):
        self.main_queue = main_queue
        self.dlq = dlq
        self.max_receive_count = max_receive_count

    def process_message(
        self,
        msg: SQSMessage,
        handler: Callable[[dict], bool]
    ) -> tuple[bool, str]:
        """Process a message with DLQ handling."""
        try:
            success = handler(msg.body)

            if success:
                self.main_queue.delete_message(msg.receipt_handle)
                return True, "processed"
            else:
                return self._handle_failure(msg, "Handler returned False")

        except Exception as e:
            return self._handle_failure(msg, str(e))

    def _handle_failure(
        self,
        msg: SQSMessage,
        error: str
    ) -> tuple[bool, str]:
        """Handle a processing failure."""
        print(f"      [Failure] Order {msg.body.get('order_id')}: receive #{msg.approximate_receive_count}, error: {error[:30]}")

        if msg.approximate_receive_count >= self.max_receive_count:
            # Move to DLQ
            print(f"      [DLQ] Moving order {msg.body.get('order_id')} to DLQ after {msg.approximate_receive_count} attempts")
            self.dlq.send_message({
                "original_body": msg.body,
                "error": error,
                "receive_count": msg.approximate_receive_count
            })
            self.main_queue.delete_message(msg.receipt_handle)
            return False, "moved_to_dlq"
        else:
            # Make message visible again for retry
            self.main_queue.make_visible_now(msg.receipt_handle)
            return False, "will_retry"


# Demo Iteration 11
print("\nDemo: Fixed SQS DLQ with Proper Message Flow")
print("-" * 40)

# Create queues with short visibility timeout
main_queue_fixed = FixedMockSQSQueue("order-processing-fixed", visibility_timeout=1)
dlq_fixed = FixedMockSQSQueue("order-processing-dlq-fixed")
dlq_handler_fixed = FixedDLQHandler(main_queue_fixed, dlq_fixed, max_receive_count=3)

def process_order_fixed(body: dict) -> bool:
    order_id = body.get("order_id")
    # Orders 2 and 3 always fail
    if order_id in [2, 3]:
        raise ValueError(f"Cannot process order {order_id}")
    return True

# Send orders
print("\nTest 1: Send orders and process with proper DLQ flow")
for i in range(1, 6):
    main_queue_fixed.send_message({"order_id": i, "amount": i * 10.0})
print(f"  Sent 5 orders to queue")

# Process until queue is empty
round_num = 0
max_rounds = 15  # Safety limit

while main_queue_fixed.get_queue_length() > 0 and round_num < max_rounds:
    round_num += 1
    msg = main_queue_fixed.receive_message()
    if msg:
        order_id = msg.body.get("order_id")
        success, disposition = dlq_handler_fixed.process_message(msg, process_order_fixed)
        if success:
            print(f"    Order {order_id}: {disposition}")

print(f"\n  Processing complete after {round_num} rounds")
print(f"  Main queue: {main_queue_fixed.get_queue_length()} messages")
print(f"  DLQ: {dlq_fixed.get_queue_length()} messages")

# Verify DLQ contents
print("\n  DLQ Contents:")
while True:
    dlq_msg = dlq_fixed.receive_message()
    if not dlq_msg:
        break
    original = dlq_msg.body.get("original_body", {})
    print(f"    - Order {original.get('order_id')}: {dlq_msg.body.get('error')[:40]}...")
    dlq_fixed.delete_message(dlq_msg.receipt_handle)

# Test 2: DLQ Recovery with transformation
print("\nTest 2: DLQ Recovery - replay with fix")

# Recreate scenario
main_queue_fixed2 = FixedMockSQSQueue("orders-v2", visibility_timeout=1)
dlq_fixed2 = FixedMockSQSQueue("orders-v2-dlq")
handler2 = FixedDLQHandler(main_queue_fixed2, dlq_fixed2, max_receive_count=2)

# Send a problematic order
main_queue_fixed2.send_message({"order_id": 99, "amount": 100.0, "needs_review": False})

# Process until it hits DLQ
processed = False
for _ in range(5):
    msg = main_queue_fixed2.receive_message()
    if msg:
        def fail_without_review(body):
            if not body.get("needs_review"):
                raise ValueError("Order requires review flag")
            return True
        success, _ = handler2.process_message(msg, fail_without_review)
        if success:
            processed = True
            break

print(f"  Original processing: {'success' if processed else 'failed -> DLQ'}")
print(f"  DLQ has: {dlq_fixed2.get_queue_length()} message(s)")

# Recovery: replay with transformation
print("\n  Replaying from DLQ with fix applied...")
recovery2 = DLQRecoveryManager(dlq_fixed2, main_queue_fixed2)

def add_review_flag(body: dict) -> dict:
    """Fix: add the missing review flag."""
    body["needs_review"] = True
    body["recovered_from_dlq"] = True
    return body

replayed, skipped = recovery2.replay_all(transform=add_review_flag)
print(f"  Replayed: {replayed} message(s)")

# Now process the fixed message
msg = main_queue_fixed2.receive_message()
if msg:
    def process_with_review(body):
        if body.get("needs_review"):
            print(f"    Processing order {body.get('order_id')} with review flag")
            return True
        return False

    success, disposition = handler2.process_message(msg, process_with_review)
    print(f"  After fix: {disposition}")
    print(f"  Final message body: {msg.body}")

print("\n  Key insight: DLQ + Transform enables recovery")
print("  - Failed messages captured with error context")
print("  - Transform function fixes the issue")
print("  - Replay puts corrected messages back in queue")


# ============================================================================
# ITERATION 12: Real Strands Agent Integration
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 12: Real Strands Agent Integration")
print("=" * 70)

# Import Strands components
try:
    from strands import Agent, tool
    from strands.models.openai import OpenAIModel
    STRANDS_AVAILABLE = True
except ImportError:
    STRANDS_AVAILABLE = False
    print("\n  [Skip] Strands SDK not available - showing pattern only")


class ResilientAgentV2:
    """Production-ready resilient agent wrapper with full recovery stack.

    Features:
    - Automatic retry on transient failures
    - Circuit breaker per model
    - Model fallback chain
    - Tool-level error recovery
    - Comprehensive metrics
    """

    def __init__(
        self,
        primary_model: str = "claude-sonnet-4",
        fallback_models: list[str] | None = None,
        recovery_config: RecoveryConfig | None = None
    ):
        self.primary_model = primary_model
        self.fallback_models = fallback_models or ["claude-3-5-haiku", "gemini-2.0-flash"]
        self.config = recovery_config or RecoveryConfig(
            max_retries=2,
            base_delay=1.0,
            circuit_failure_threshold=3
        )
        self.recovery_stack = RecoveryStack(self.config)
        self.current_model = primary_model
        self.call_count = 0
        self.fallback_count = 0

    def _create_model(self, model_id: str) -> "OpenAIModel":
        """Create a model instance for the given model ID."""
        return OpenAIModel(
            model_id=model_id,
            client_args={
                "base_url": "http://localhost:4000",
                "api_key": "sk-local"
            }
        )

    def _create_agent(self, model_id: str, tools: list | None = None, system_prompt: str | None = None) -> "Agent":
        """Create an agent with the specified model."""
        model = self._create_model(model_id)
        return Agent(
            model=model,
            tools=tools or [],
            system_prompt=system_prompt,
            callback_handler=None  # Disable streaming for cleaner output
        )

    def __call__(
        self,
        prompt: str,
        tools: list | None = None,
        system_prompt: str | None = None
    ) -> str:
        """Execute prompt with full recovery stack."""
        self.call_count += 1

        # Build model chain: primary + fallbacks
        model_chain = [self.primary_model] + self.fallback_models

        last_error = None

        for i, model_id in enumerate(model_chain):
            try:
                # Use recovery stack for each model attempt
                result = self.recovery_stack.execute(
                    operation_name=f"agent_call_{model_id}",
                    func=lambda: self._execute_with_model(model_id, prompt, tools, system_prompt),
                    service_name=f"llm_{model_id.replace('-', '_')}"
                )
                self.current_model = model_id
                if i > 0:
                    self.fallback_count += 1
                    print(f"  [ResilientAgent] Used fallback model: {model_id}")
                return result

            except CircuitOpenError as e:
                print(f"  [ResilientAgent] Circuit open for {model_id}, trying next...")
                last_error = e
                continue

            except Exception as e:
                print(f"  [ResilientAgent] {model_id} failed after retries: {e}")
                last_error = e
                continue

        raise RuntimeError(f"All models failed. Last error: {last_error}")

    def _execute_with_model(
        self,
        model_id: str,
        prompt: str,
        tools: list | None,
        system_prompt: str | None
    ) -> str:
        """Execute a single call with the specified model."""
        agent = self._create_agent(model_id, tools, system_prompt)
        result = agent(prompt)
        return str(result)

    def get_stats(self) -> dict:
        """Get agent statistics."""
        return {
            "total_calls": self.call_count,
            "fallback_count": self.fallback_count,
            "current_model": self.current_model,
            "recovery_metrics": self.recovery_stack.get_metrics().__dict__
        }


# Demo Iteration 12
print("\nDemo: Real Strands Agent with Recovery")
print("-" * 40)

if STRANDS_AVAILABLE:
    # Test 1: Basic resilient agent call
    print("\nTest 1: Basic resilient agent call")

    resilient_agent = ResilientAgentV2(
        primary_model="claude-sonnet-4",
        fallback_models=["claude-3-5-haiku"],
        recovery_config=RecoveryConfig(max_retries=1, base_delay=0.5)
    )

    try:
        # Simple prompt that should succeed
        response = resilient_agent(
            "What is 2 + 2? Reply with just the number.",
            system_prompt="You are a helpful math assistant. Be concise."
        )
        print(f"  Response: {response[:100]}...")
        print(f"  Model used: {resilient_agent.current_model}")
    except Exception as e:
        print(f"  Error: {e}")

    # Test 2: Agent with tools
    print("\nTest 2: Resilient agent with tools")

    @tool
    def calculate(expression: str) -> str:
        """Evaluate a mathematical expression safely."""
        try:
            # Simple safe eval for basic math
            allowed = set("0123456789+-*/.(). ")
            if all(c in allowed for c in expression):
                result = eval(expression)
                return f"Result: {result}"
            return "Error: Invalid expression"
        except Exception as e:
            return f"Error: {e}"

    @tool
    def get_current_time() -> str:
        """Get the current time."""
        from datetime import datetime
        return f"Current time: {datetime.now().strftime('%H:%M:%S')}"

    try:
        response = resilient_agent(
            "What is 15 * 7? Use the calculate tool.",
            tools=[calculate, get_current_time],
            system_prompt="You are a helpful assistant. Use tools when needed."
        )
        print(f"  Response: {response[:150]}...")
    except Exception as e:
        print(f"  Error: {e}")

    # Test 3: Simulated failure with fallback
    print("\nTest 3: Simulated model failure (force fallback)")

    # Create agent with a non-existent primary model to force fallback
    fallback_agent = ResilientAgentV2(
        primary_model="non-existent-model",  # Will fail
        fallback_models=["claude-3-5-haiku"],
        recovery_config=RecoveryConfig(max_retries=0, base_delay=0.1)  # No retries for speed
    )

    try:
        response = fallback_agent(
            "Say 'Hello from fallback!' and nothing else.",
            system_prompt="Be extremely concise."
        )
        print(f"  Response: {response[:100]}...")
        print(f"  Model used: {fallback_agent.current_model}")
        print(f"  Fallback count: {fallback_agent.fallback_count}")
    except Exception as e:
        print(f"  All models failed: {e}")

    # Show stats
    print("\nAgent Statistics:")
    stats = resilient_agent.get_stats()
    print(f"  Total calls: {stats['total_calls']}")
    print(f"  Fallback count: {stats['fallback_count']}")
    print(f"  Current model: {stats['current_model']}")

else:
    # Show the pattern without actual execution
    print("\n  Pattern: ResilientAgentV2 wraps Strands Agent with:")
    print("  - RecoveryStack for retry + circuit breaker")
    print("  - Model fallback chain (primary -> fallbacks)")
    print("  - Per-model circuit breakers")
    print("  - Comprehensive metrics tracking")

    print("\n  Example usage:")
    print("  ```python")
    print("  agent = ResilientAgentV2(")
    print("      primary_model='claude-sonnet-4',")
    print("      fallback_models=['claude-3-5-haiku', 'gemini-flash']")
    print("  )")
    print("  response = agent('Your prompt here', tools=[my_tool])")
    print("  ```")

    print("\n  Mock demonstration of fallback behavior:")

    # Simulate the behavior without actual API calls
    class MockResilientAgent:
        def __init__(self):
            self.models = ["claude-sonnet-4", "claude-3-5-haiku"]
            self.call_count = 0
            self.current_model = None

        def __call__(self, prompt: str) -> str:
            self.call_count += 1
            # Simulate: first model fails, second succeeds
            for i, model in enumerate(self.models):
                if i == 0:
                    print(f"    [{model}] Simulated failure: rate limited")
                    continue
                self.current_model = model
                print(f"    [{model}] Success!")
                return f"Mock response from {model}"
            return "All failed"

    mock_agent = MockResilientAgent()
    result = mock_agent("Test prompt")
    print(f"  Result: {result}")
    print(f"  Model used: {mock_agent.current_model}")

print("\n  Key insight: ResilientAgent provides transparent recovery")
print("  - Automatic retry on transient failures")
print("  - Circuit breaker prevents hammering failed services")
print("  - Model fallback ensures response even if primary fails")
print("  - Metrics track recovery behavior for monitoring")


print("\n" + "=" * 70)
print("LEVEL 23 COMPLETE: Error Recovery (12 Iterations)")
print("=" * 70)

print("""
Summary - Error Recovery Patterns:

TIER 1: Local Patterns (Iterations 1-5)
  1. Retry with Exponential Backoff
     - Configurable delay, jitter, max delay
     - Decorator and executor patterns

  2. Failure Classification
     - TRANSIENT, PERMANENT, RATE_LIMITED, TIMEOUT
     - Pattern matching on errors and HTTP codes

  3. Retry Policies (Strategy)
     - AlwaysRetry, TransientOnly, BudgetAware, Adaptive
     - Right policy for right scenario

  4. Fallback Chains
     - Service fallbacks (primary -> backup -> cache)
     - Model fallbacks (expensive -> cheap)
     - Graceful degradation (full -> summary -> error)

  5. Circuit Breaker
     - CLOSED -> OPEN -> HALF_OPEN states
     - Prevents cascade failures

TIER 2: Stateful Recovery (Iterations 6-7)
  6. Checkpoint & Resume
     - Save state after each step
     - Resume from last checkpoint on failure

  7. Human Escalation
     - Metric-based triggers
     - Multi-channel notifications
     - Human-in-the-loop decisions

TIER 3: AWS-Native Patterns (Iterations 8-9)
  8. SQS Dead-Letter Queues
     - Failed messages captured for analysis
     - Bulk replay with transformation

  9. Step Functions Retry
     - Declarative retry configuration
     - ErrorEquals pattern matching
     - Catch blocks for error handling

TIER 4: Production Integration (Iteration 10)
  10. Unified RecoveryStack
      - Single facade for all recovery patterns
      - Composable configuration
      - Comprehensive metrics and status

TIER 5: Validation & Integration (Iterations 11-12)
  11. Fixed SQS DLQ Demo
      - Proper message flow: queue -> retry -> DLQ
      - DLQ recovery with transformation
      - Verified end-to-end message lifecycle

  12. Real Strands Agent Integration
      - ResilientAgentV2 wrapper with full recovery
      - Model fallback chain (primary -> fallbacks)
      - Tool support with error recovery
      - Production-ready agent pattern

Key Learnings:
  - Classify failures before deciding to retry
  - Circuit breakers prevent cascade failures
  - Fallbacks provide graceful degradation
  - Checkpoints enable reliable long-running workflows
  - Human escalation is the ultimate safety net
  - DLQ captures failed work for later recovery
  - Step Functions patterns are declarative and composable
  - ResilientAgent wraps Strands Agent with transparent recovery
  - Transform functions enable DLQ message repair and replay
""")
