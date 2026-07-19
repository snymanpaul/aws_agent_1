"""
Level 24: Tool Synthesis

Agents that CREATE tools at runtime through code generation, validation,
and sandboxed execution.

12 Iterations:
1. Natural Language to Code Generator
2. Code Validation and Security Scanning
3. Basic Subprocess Sandbox
4. Docker Container Sandbox
5. Runtime Tool Registration and Lifecycle
6. Capability-Based Permissions
7. Multi-Step Synthesis Workflow
8. Observability Integration (L21)
9. Recovery Integration (L23)
10. Tool Versioning and A/B Testing
11. Graphiti Persistence
12. Unified ToolSynthesizer Facade

Key Safety Requirement: All synthesized code runs in sandboxed environments
(subprocess with limits, or Docker container for higher risk).
"""

import ast
import json
import re
import subprocess
import sys
import tempfile
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field
from strands import Agent, tool

# Import shared model helper
sys.path.insert(0, str(Path(__file__).parent.parent))
from tools import get_model

# ============================================================================
# ITERATION 1: Natural Language to Code Generator
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 1: Natural Language to Code Generator")
print("=" * 70)


class ParameterSpec(BaseModel):
    """Specification for a tool parameter."""

    name: str = Field(description="Parameter name (valid Python identifier)")
    param_type: str = Field(description="Python type hint (str, int, float, list, dict)")
    description: str = Field(description="What this parameter represents")
    required: bool = Field(default=True, description="Whether parameter is required")
    default: Any = Field(default=None, description="Default value if not required")


class ToolSpec(BaseModel):
    """Natural language specification for a tool to synthesize."""

    name: str = Field(description="Tool function name (valid Python identifier)")
    description: str = Field(description="What the tool does (becomes docstring)")
    parameters: list[ParameterSpec] = Field(description="Tool parameters")
    return_type: str = Field(default="str", description="Return type hint")
    examples: list[str] = Field(default_factory=list, description="Example usages")


class GeneratedTool(BaseModel):
    """Output from code generation."""

    source_code: str = Field(description="Complete Python function code")
    imports: list[str] = Field(default_factory=list, description="Required imports")
    dependencies: list[str] = Field(default_factory=list, description="pip packages needed")
    test_cases: list[dict] = Field(default_factory=list, description="Test cases with inputs/outputs")


class CodeGenerator:
    """LLM-powered tool code generator.

    Uses structured output to ensure valid Python function generation.
    """

    def __init__(self, model_alias: str = "haiku"):
        """Initialize with specified model.

        Args:
            model_alias: Model to use for generation (haiku for speed, sonnet for quality)
        """
        self.model = get_model(model_alias)
        self.agent = Agent(
            model=self.model,
            system_prompt=self._get_system_prompt(),
            callback_handler=None,
        )

    def _get_system_prompt(self) -> str:
        return """You are a Python code generator that creates tool functions.

Your task is to generate clean, safe, pure Python functions based on specifications.

RULES:
1. Generate ONLY the function code - no imports outside the function
2. Include a docstring with parameter descriptions
3. Use type hints for all parameters and return type
4. Keep functions pure when possible (no side effects)
5. Handle edge cases gracefully
6. Return meaningful error messages as strings (not exceptions)
7. DO NOT use: os, subprocess, eval, exec, open, __import__, compile
8. DO NOT access network, files, or system resources
9. Keep code simple and readable

ALWAYS respond with valid Python code wrapped in ```python code blocks.
The function should be complete and runnable."""

    def generate(self, spec: ToolSpec, debug: bool = False) -> GeneratedTool:
        """Generate tool code from specification.

        Args:
            spec: Tool specification with name, description, parameters
            debug: If True, print raw LLM response

        Returns:
            GeneratedTool with source code and metadata
        """
        # Build the prompt
        prompt = self._build_prompt(spec)

        # Generate code
        result = self.agent(prompt)

        if debug:
            print(f"[DEBUG] Raw response type: {type(result.message)}")
            print(f"[DEBUG] Raw response: {result.message[:500] if isinstance(result.message, str) else result.message}")

        # Parse response
        return self._parse_response(result.message, spec)

    def _build_prompt(self, spec: ToolSpec) -> str:
        params_desc = "\n".join(
            f"  - {p.name} ({p.param_type}): {p.description}"
            + (f" [default: {p.default}]" if not p.required else " [required]")
            for p in spec.parameters
        )

        examples_desc = (
            "\n".join(f"  - {ex}" for ex in spec.examples) if spec.examples else "  (none provided)"
        )

        return f"""Write a Python function with this specification:

FUNCTION NAME: {spec.name}
DESCRIPTION: {spec.description}
PARAMETERS:
{params_desc}
RETURN TYPE: {spec.return_type}
EXAMPLE USAGES:
{examples_desc}

Write the complete function in a ```python code block."""

    def _parse_response(self, response: Any, spec: ToolSpec) -> GeneratedTool:
        """Parse LLM response into GeneratedTool."""
        # Handle dict response from LLM (Strands format)
        if isinstance(response, dict):
            # Check for Strands message format: {'role': 'assistant', 'content': [{'text': '...'}]}
            if "content" in response and isinstance(response["content"], list):
                content_parts = response["content"]
                text_parts = [p.get("text", "") for p in content_parts if isinstance(p, dict) and "text" in p]
                response_str = "\n".join(text_parts)
            # Check for direct source_code format
            elif "source_code" in response:
                return GeneratedTool(
                    source_code=response.get("source_code", ""),
                    imports=response.get("imports", []),
                    dependencies=response.get("dependencies", []),
                    test_cases=response.get("test_cases", []),
                )
            else:
                response_str = str(response)
        else:
            # Convert to string if needed
            response_str = str(response)

        # Try to extract JSON from response
        try:
            # Look for JSON block
            json_match = re.search(r"\{[\s\S]*\}", response_str)
            if json_match:
                data = json.loads(json_match.group())
                return GeneratedTool(
                    source_code=data.get("source_code", ""),
                    imports=data.get("imports", []),
                    dependencies=data.get("dependencies", []),
                    test_cases=data.get("test_cases", []),
                )
        except json.JSONDecodeError:
            pass

        # Fallback: try to extract code block
        code_match = re.search(r"```python\n([\s\S]*?)```", response_str)
        if code_match:
            return GeneratedTool(
                source_code=code_match.group(1).strip(),
                imports=[],
                dependencies=[],
                test_cases=[],
            )

        # Last resort: return raw response as code
        return GeneratedTool(source_code=response_str, imports=[], dependencies=[], test_cases=[])


# Demo: Generate a compound interest calculator
print("\nGenerating compound interest calculator tool...")

spec = ToolSpec(
    name="calculate_compound_interest",
    description="Calculate compound interest on a principal amount over time",
    parameters=[
        ParameterSpec(
            name="principal",
            param_type="float",
            description="Initial investment amount",
            required=True,
        ),
        ParameterSpec(
            name="rate",
            param_type="float",
            description="Annual interest rate as decimal (e.g., 0.05 for 5%)",
            required=True,
        ),
        ParameterSpec(
            name="years",
            param_type="int",
            description="Number of years to compound",
            required=True,
        ),
        ParameterSpec(
            name="compounds_per_year",
            param_type="int",
            description="Number of times interest compounds per year",
            required=False,
            default=12,
        ),
    ],
    return_type="dict",
    examples=[
        "calculate_compound_interest(1000, 0.05, 10) -> {'final_amount': 1647.01, 'interest_earned': 647.01}",
        "calculate_compound_interest(5000, 0.08, 5, 4) -> quarterly compounding result",
    ],
)

generator = CodeGenerator(model_alias="haiku")
generated = generator.generate(spec)

print(f"\nGenerated code:\n{'-' * 40}")
print(generated.source_code)
print(f"{'-' * 40}")
print(f"Imports needed: {generated.imports}")
print(f"Test cases: {len(generated.test_cases)}")


# ============================================================================
# ITERATION 2: Code Validation and Security Scanning
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 2: Code Validation and Security Scanning")
print("=" * 70)


class SecuritySeverity(str, Enum):
    """Severity levels for security issues."""

    CRITICAL = "critical"  # Immediate block
    HIGH = "high"  # Block with warning
    MEDIUM = "medium"  # Warning, may proceed
    LOW = "low"  # Informational


@dataclass
class SecurityPattern:
    """A pattern to detect in generated code."""

    pattern: str  # Regex pattern
    severity: SecuritySeverity
    description: str
    recommendation: str


class ValidationResult(BaseModel):
    """Result of code validation."""

    valid: bool = Field(description="Whether code is valid")
    syntax_valid: bool = Field(default=True, description="Syntax check passed")
    ast_valid: bool = Field(default=True, description="AST analysis passed")
    security_valid: bool = Field(default=True, description="Security scan passed")
    errors: list[str] = Field(default_factory=list, description="Critical errors")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking warnings")
    risk_score: float = Field(default=0.0, description="0.0 (safe) to 1.0 (dangerous)")


class SecurityScanner:
    """Detect dangerous patterns in generated code.

    Uses regex patterns and AST analysis to identify security risks.
    """

    # Blocked patterns ordered by severity
    PATTERNS: list[SecurityPattern] = [
        # CRITICAL - Immediate block
        SecurityPattern(
            pattern=r"\beval\s*\(",
            severity=SecuritySeverity.CRITICAL,
            description="Dynamic code execution via eval()",
            recommendation="Use ast.literal_eval() for safe evaluation",
        ),
        SecurityPattern(
            pattern=r"\bexec\s*\(",
            severity=SecuritySeverity.CRITICAL,
            description="Dynamic code execution via exec()",
            recommendation="Avoid dynamic execution entirely",
        ),
        SecurityPattern(
            pattern=r"\b__import__\s*\(",
            severity=SecuritySeverity.CRITICAL,
            description="Dynamic import bypassing static analysis",
            recommendation="Use explicit imports",
        ),
        SecurityPattern(
            pattern=r"\bcompile\s*\(",
            severity=SecuritySeverity.CRITICAL,
            description="Code compilation for dynamic execution",
            recommendation="Avoid runtime code compilation",
        ),
        # HIGH - Block with warning
        SecurityPattern(
            pattern=r"\bos\s*\.\s*system\s*\(",
            severity=SecuritySeverity.HIGH,
            description="Shell command execution via os.system()",
            recommendation="Avoid system commands in generated tools",
        ),
        SecurityPattern(
            pattern=r"\bsubprocess\s*\.",
            severity=SecuritySeverity.HIGH,
            description="Subprocess execution",
            recommendation="Avoid subprocess calls in generated tools",
        ),
        SecurityPattern(
            pattern=r"\bimport\s+os\b",
            severity=SecuritySeverity.HIGH,
            description="OS module import enables file/process access",
            recommendation="Avoid os module entirely",
        ),
        SecurityPattern(
            pattern=r"\bimport\s+subprocess\b",
            severity=SecuritySeverity.HIGH,
            description="Subprocess module import",
            recommendation="Avoid subprocess module entirely",
        ),
        SecurityPattern(
            pattern=r"\bimport\s+shutil\b",
            severity=SecuritySeverity.HIGH,
            description="File operations module",
            recommendation="Avoid file operations in generated tools",
        ),
        # MEDIUM - Warning
        SecurityPattern(
            pattern=r"\bopen\s*\(",
            severity=SecuritySeverity.MEDIUM,
            description="File access via open()",
            recommendation="Generated tools should not access files",
        ),
        SecurityPattern(
            pattern=r"\bimport\s+socket\b",
            severity=SecuritySeverity.MEDIUM,
            description="Network socket access",
            recommendation="Avoid network access in generated tools",
        ),
        SecurityPattern(
            pattern=r"\bimport\s+requests\b",
            severity=SecuritySeverity.MEDIUM,
            description="HTTP requests library",
            recommendation="Avoid network requests in generated tools",
        ),
        SecurityPattern(
            pattern=r"\bimport\s+urllib\b",
            severity=SecuritySeverity.MEDIUM,
            description="URL library with network access",
            recommendation="Avoid network access in generated tools",
        ),
        # LOW - Informational
        SecurityPattern(
            pattern=r"\bglobals\s*\(\s*\)",
            severity=SecuritySeverity.LOW,
            description="Access to global namespace",
            recommendation="Avoid globals() for cleaner code",
        ),
        SecurityPattern(
            pattern=r"\blocals\s*\(\s*\)",
            severity=SecuritySeverity.LOW,
            description="Access to local namespace",
            recommendation="Avoid locals() for cleaner code",
        ),
    ]

    # Allowed standard library imports
    ALLOWED_IMPORTS = {"math", "json", "re", "datetime", "typing", "decimal", "fractions", "statistics"}

    def scan(self, code: str) -> list[tuple[SecurityPattern, str]]:
        """Scan code for security issues.

        Args:
            code: Python source code to scan

        Returns:
            List of (pattern, matched_text) tuples for violations found
        """
        violations = []
        for pattern in self.PATTERNS:
            matches = re.finditer(pattern.pattern, code)
            for match in matches:
                violations.append((pattern, match.group()))
        return violations

    def calculate_risk_score(self, violations: list[tuple[SecurityPattern, str]]) -> float:
        """Calculate risk score from violations.

        Args:
            violations: List of detected violations

        Returns:
            Risk score from 0.0 (safe) to 1.0 (dangerous)
        """
        if not violations:
            return 0.0

        # Weight by severity
        severity_weights = {
            SecuritySeverity.CRITICAL: 1.0,
            SecuritySeverity.HIGH: 0.7,
            SecuritySeverity.MEDIUM: 0.4,
            SecuritySeverity.LOW: 0.1,
        }

        total_weight = sum(severity_weights[v[0].severity] for v in violations)
        # Normalize to 0-1 (cap at 1.0)
        return min(1.0, total_weight / 2.0)


class ASTValidator:
    """Validate code using AST analysis."""

    # Disallowed AST node types
    DISALLOWED_NODES = {
        "Import": ["os", "subprocess", "shutil", "socket"],
        "ImportFrom": ["os", "subprocess", "shutil", "socket"],
    }

    def validate(self, code: str) -> tuple[bool, list[str]]:
        """Validate code AST structure.

        Args:
            code: Python source code

        Returns:
            Tuple of (valid, list of errors)
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, [f"Syntax error: {e}"]

        errors = []
        for node in ast.walk(tree):
            # Check imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in self.DISALLOWED_NODES.get("Import", []):
                        errors.append(f"Disallowed import: {alias.name}")

            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in self.DISALLOWED_NODES.get(
                    "ImportFrom", []
                ):
                    errors.append(f"Disallowed import from: {node.module}")

            # Check for dangerous function calls
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ("eval", "exec", "compile", "__import__"):
                        errors.append(f"Dangerous function call: {node.func.id}()")

        return len(errors) == 0, errors


class CodeValidator:
    """Multi-layer validation for generated code."""

    def __init__(self):
        self.security_scanner = SecurityScanner()
        self.ast_validator = ASTValidator()

    def validate(self, code: str) -> ValidationResult:
        """Perform full validation on generated code.

        Args:
            code: Python source code to validate

        Returns:
            ValidationResult with detailed findings
        """
        errors = []
        warnings = []

        # Layer 1: Syntax check
        try:
            compile(code, "<generated>", "exec")
            syntax_valid = True
        except SyntaxError as e:
            syntax_valid = False
            errors.append(f"Syntax error at line {e.lineno}: {e.msg}")

        # Layer 2: AST validation
        ast_valid, ast_errors = self.ast_validator.validate(code)
        errors.extend(ast_errors)

        # Layer 3: Security scan
        violations = self.security_scanner.scan(code)
        security_valid = True

        for pattern, matched in violations:
            if pattern.severity in (SecuritySeverity.CRITICAL, SecuritySeverity.HIGH):
                security_valid = False
                errors.append(f"[{pattern.severity.value}] {pattern.description}: '{matched}'")
            else:
                warnings.append(f"[{pattern.severity.value}] {pattern.description}: '{matched}'")

        # Calculate risk score
        risk_score = self.security_scanner.calculate_risk_score(violations)

        return ValidationResult(
            valid=syntax_valid and ast_valid and security_valid,
            syntax_valid=syntax_valid,
            ast_valid=ast_valid,
            security_valid=security_valid,
            errors=errors,
            warnings=warnings,
            risk_score=risk_score,
        )


# Demo: Validate generated code and unsafe code
print("\nValidating generated code...")

validator = CodeValidator()

# Validate the previously generated code
result = validator.validate(generated.source_code)
print(f"\nGenerated code validation:")
print(f"  Valid: {result.valid}")
print(f"  Risk score: {result.risk_score:.2f}")
if result.errors:
    print(f"  Errors: {result.errors}")
if result.warnings:
    print(f"  Warnings: {result.warnings}")

# Test with intentionally unsafe code
unsafe_code = '''
def dangerous_function(cmd: str) -> str:
    """Execute a shell command."""
    import os
    return os.system(cmd)
'''

unsafe_result = validator.validate(unsafe_code)
print(f"\nUnsafe code validation:")
print(f"  Valid: {unsafe_result.valid}")
print(f"  Risk score: {unsafe_result.risk_score:.2f}")
print(f"  Errors: {unsafe_result.errors}")

# Test with eval
eval_code = '''
def compute(expression: str) -> float:
    """Evaluate a math expression."""
    return eval(expression)
'''

eval_result = validator.validate(eval_code)
print(f"\nEval code validation:")
print(f"  Valid: {eval_result.valid}")
print(f"  Risk score: {eval_result.risk_score:.2f}")
print(f"  Errors: {eval_result.errors}")


# ============================================================================
# ITERATION 3: Basic Subprocess Sandbox
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 3: Basic Subprocess Sandbox")
print("=" * 70)


@dataclass
class ResourceLimits:
    """Resource constraints for sandbox execution."""

    timeout_seconds: float = 5.0  # Max execution time
    memory_mb: int = 100  # Max memory (advisory)


class SandboxResult(BaseModel):
    """Result of sandboxed execution."""

    success: bool = Field(description="Whether execution succeeded")
    result: Any = Field(default=None, description="Function return value")
    stdout: str = Field(default="", description="Captured stdout")
    stderr: str = Field(default="", description="Captured stderr")
    execution_time_ms: float = Field(default=0.0, description="Execution time in ms")
    exit_code: int = Field(default=0, description="Process exit code")
    error: str | None = Field(default=None, description="Error message if failed")


class SubprocessSandbox:
    """Execute untrusted code in isolated subprocess.

    Provides basic isolation through process boundaries with resource limits.
    """

    def __init__(self, limits: ResourceLimits | None = None):
        """Initialize sandbox with resource limits.

        Args:
            limits: Resource constraints (timeout, memory)
        """
        self.limits = limits or ResourceLimits()

    def execute(
        self,
        code: str,
        function_name: str,
        *args,
        **kwargs,
    ) -> SandboxResult:
        """Execute a function from generated code in subprocess.

        Args:
            code: Python source code containing the function
            function_name: Name of function to call
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function

        Returns:
            SandboxResult with execution outcome
        """
        start_time = time.time()

        # Build the execution script
        script = self._build_script(code, function_name, args, kwargs)

        # Write to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script)
            script_path = f.name

        try:
            # Execute in subprocess with timeout
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=self.limits.timeout_seconds,
            )

            execution_time = (time.time() - start_time) * 1000

            # Parse result from stdout
            if result.returncode == 0:
                # Try to parse JSON result from last line
                try:
                    output_lines = result.stdout.strip().split("\n")
                    if output_lines:
                        parsed_result = json.loads(output_lines[-1])
                        return SandboxResult(
                            success=True,
                            result=parsed_result,
                            stdout="\n".join(output_lines[:-1]),
                            stderr=result.stderr,
                            execution_time_ms=execution_time,
                            exit_code=result.returncode,
                        )
                except json.JSONDecodeError:
                    pass

                return SandboxResult(
                    success=True,
                    result=result.stdout.strip(),
                    stdout=result.stdout,
                    stderr=result.stderr,
                    execution_time_ms=execution_time,
                    exit_code=result.returncode,
                )
            else:
                return SandboxResult(
                    success=False,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    execution_time_ms=execution_time,
                    exit_code=result.returncode,
                    error=result.stderr or f"Exit code: {result.returncode}",
                )

        except subprocess.TimeoutExpired:
            execution_time = (time.time() - start_time) * 1000
            return SandboxResult(
                success=False,
                execution_time_ms=execution_time,
                exit_code=-1,
                error=f"Timeout after {self.limits.timeout_seconds}s",
            )
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            return SandboxResult(
                success=False,
                execution_time_ms=execution_time,
                exit_code=-1,
                error=str(e),
            )
        finally:
            # Cleanup temp file
            Path(script_path).unlink(missing_ok=True)

    def _build_script(
        self,
        code: str,
        function_name: str,
        args: tuple,
        kwargs: dict,
    ) -> str:
        """Build the execution script.

        Args:
            code: Function source code
            function_name: Name of function to call
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Complete Python script to execute
        """
        args_json = json.dumps(args)
        kwargs_json = json.dumps(kwargs)

        return f'''
import json
import sys

# Generated function code
{code}

# Execute and output result
if __name__ == "__main__":
    try:
        args = json.loads({repr(args_json)})
        kwargs = json.loads({repr(kwargs_json)})
        result = {function_name}(*args, **kwargs)
        print(json.dumps(result))
    except Exception as e:
        print(f"Error: {{e}}", file=sys.stderr)
        sys.exit(1)
'''


# Demo: Execute generated code in sandbox
print("\nExecuting generated code in subprocess sandbox...")

# First, let's create a simple known-good function for testing
test_code = '''
def calculate_compound_interest(principal: float, rate: float, years: int, compounds_per_year: int = 12) -> dict:
    """Calculate compound interest on a principal amount.

    Args:
        principal: Initial investment amount
        rate: Annual interest rate as decimal (e.g., 0.05 for 5%)
        years: Number of years to compound
        compounds_per_year: Number of times interest compounds per year

    Returns:
        Dictionary with final_amount and interest_earned
    """
    # Compound interest formula: A = P(1 + r/n)^(nt)
    final_amount = principal * (1 + rate / compounds_per_year) ** (compounds_per_year * years)
    interest_earned = final_amount - principal

    return {
        "final_amount": round(final_amount, 2),
        "interest_earned": round(interest_earned, 2)
    }
'''

sandbox = SubprocessSandbox(limits=ResourceLimits(timeout_seconds=5.0))

# Execute the function
result = sandbox.execute(
    test_code,
    "calculate_compound_interest",
    1000.0,  # principal
    0.05,  # rate (5%)
    10,  # years
    compounds_per_year=12,
)

print(f"\nExecution result:")
print(f"  Success: {result.success}")
print(f"  Result: {result.result}")
print(f"  Execution time: {result.execution_time_ms:.2f}ms")
if result.error:
    print(f"  Error: {result.error}")

# Test with different inputs
result2 = sandbox.execute(
    test_code,
    "calculate_compound_interest",
    5000.0,  # principal
    0.08,  # rate (8%)
    5,  # years
    compounds_per_year=4,  # quarterly
)

print(f"\nSecond execution (quarterly compounding):")
print(f"  Success: {result2.success}")
print(f"  Result: {result2.result}")

# Test timeout with infinite loop
timeout_code = '''
def infinite_loop() -> str:
    """This will timeout."""
    while True:
        pass
    return "never reached"
'''

print("\nTesting timeout protection...")
timeout_result = sandbox.execute(timeout_code, "infinite_loop")
print(f"  Success: {timeout_result.success}")
print(f"  Error: {timeout_result.error}")
print(f"  Execution time: {timeout_result.execution_time_ms:.2f}ms")


# ============================================================================
# COMBINED DEMO: Full Synthesis Pipeline (Iterations 1-3)
# ============================================================================
print("\n" + "=" * 70)
print("COMBINED DEMO: Full Synthesis Pipeline")
print("=" * 70)


def synthesize_and_execute(spec: ToolSpec, *args, **kwargs) -> dict:
    """Full pipeline: generate -> validate -> execute.

    Args:
        spec: Tool specification
        *args: Arguments for the synthesized function
        **kwargs: Keyword arguments for the function

    Returns:
        Dictionary with synthesis and execution results
    """
    print(f"\n1. Generating code for: {spec.name}")

    # Generate code
    generator = CodeGenerator(model_alias="haiku")
    generated = generator.generate(spec)

    print(f"   Generated {len(generated.source_code)} chars of code")

    # Validate
    print("2. Validating generated code...")
    validator = CodeValidator()
    validation = validator.validate(generated.source_code)

    print(f"   Valid: {validation.valid}, Risk: {validation.risk_score:.2f}")

    if not validation.valid:
        return {
            "success": False,
            "phase": "validation",
            "errors": validation.errors,
        }

    # Execute in sandbox
    print("3. Executing in sandbox...")
    sandbox = SubprocessSandbox()
    result = sandbox.execute(generated.source_code, spec.name, *args, **kwargs)

    print(f"   Execution success: {result.success}")

    return {
        "success": result.success,
        "phase": "execution",
        "result": result.result,
        "execution_time_ms": result.execution_time_ms,
        "code": generated.source_code,
        "risk_score": validation.risk_score,
    }


# Test the full pipeline
print("\nRunning full synthesis pipeline for fibonacci calculator...")

fib_spec = ToolSpec(
    name="fibonacci",
    description="Calculate the nth Fibonacci number",
    parameters=[
        ParameterSpec(
            name="n",
            param_type="int",
            description="Position in Fibonacci sequence (0-indexed)",
            required=True,
        ),
    ],
    return_type="int",
    examples=[
        "fibonacci(0) -> 0",
        "fibonacci(1) -> 1",
        "fibonacci(10) -> 55",
    ],
)

pipeline_result = synthesize_and_execute(fib_spec, 10)
print(f"\nPipeline result:")
print(f"  Success: {pipeline_result['success']}")
print(f"  Result: {pipeline_result.get('result')}")
print(f"  Execution time: {pipeline_result.get('execution_time_ms', 0):.2f}ms")

print("\n" + "=" * 70)
print("ITERATIONS 1-3 COMPLETE")
print("=" * 70)


# ============================================================================
# ITERATION 4: Docker Container Sandbox
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 4: Docker Container Sandbox")
print("=" * 70)


@dataclass
class DockerConfig:
    """Configuration for Docker sandbox."""

    image: str = "python:3.11-slim"
    network_mode: str = "none"  # No network access
    memory_limit: str = "100m"  # 100MB memory limit
    cpu_period: int = 100000
    cpu_quota: int = 50000  # 50% CPU limit
    read_only: bool = True  # Read-only filesystem
    auto_remove: bool = True  # Remove container after execution
    timeout_seconds: float = 10.0


class DockerSandbox:
    """Execute untrusted code in ephemeral Docker container.

    Provides maximum isolation using Docker with:
    - Network disabled
    - Memory limits
    - CPU limits
    - Read-only filesystem
    - Auto-cleanup
    """

    def __init__(self, config: DockerConfig | None = None):
        """Initialize Docker sandbox.

        Args:
            config: Docker configuration options
        """
        self.config = config or DockerConfig()
        self._check_docker_available()

    def _check_docker_available(self) -> bool:
        """Check if Docker is available."""
        try:
            result = subprocess.run(
                ["docker", "version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def execute(
        self,
        code: str,
        function_name: str,
        *args,
        **kwargs,
    ) -> SandboxResult:
        """Execute code in Docker container.

        Args:
            code: Python source code containing the function
            function_name: Name of function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            SandboxResult with execution outcome
        """
        start_time = time.time()

        # Build execution script
        script = self._build_script(code, function_name, args, kwargs)

        # Create temp file for the script
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script)
            script_path = f.name

        try:
            # Build docker command
            cmd = [
                "docker", "run",
                "--rm",  # Remove after execution
                f"--network={self.config.network_mode}",
                f"--memory={self.config.memory_limit}",
                f"--cpu-period={self.config.cpu_period}",
                f"--cpu-quota={self.config.cpu_quota}",
                "-v", f"{script_path}:/app/script.py:ro",  # Mount script read-only
                "-w", "/app",
                self.config.image,
                "python", "/app/script.py",
            ]

            if self.config.read_only:
                # Add tmpfs for /tmp since we need somewhere writable for Python
                cmd.insert(-3, "--read-only")
                cmd.insert(-3, "--tmpfs")
                cmd.insert(-3, "/tmp")

            # Execute
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
            )

            execution_time = (time.time() - start_time) * 1000

            # Parse result
            if result.returncode == 0:
                try:
                    output_lines = result.stdout.strip().split("\n")
                    if output_lines:
                        parsed_result = json.loads(output_lines[-1])
                        return SandboxResult(
                            success=True,
                            result=parsed_result,
                            stdout="\n".join(output_lines[:-1]),
                            stderr=result.stderr,
                            execution_time_ms=execution_time,
                            exit_code=result.returncode,
                        )
                except json.JSONDecodeError:
                    pass

                return SandboxResult(
                    success=True,
                    result=result.stdout.strip(),
                    stdout=result.stdout,
                    stderr=result.stderr,
                    execution_time_ms=execution_time,
                    exit_code=result.returncode,
                )
            else:
                return SandboxResult(
                    success=False,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    execution_time_ms=execution_time,
                    exit_code=result.returncode,
                    error=result.stderr or f"Exit code: {result.returncode}",
                )

        except subprocess.TimeoutExpired:
            execution_time = (time.time() - start_time) * 1000
            return SandboxResult(
                success=False,
                execution_time_ms=execution_time,
                exit_code=-1,
                error=f"Docker timeout after {self.config.timeout_seconds}s",
            )
        except FileNotFoundError:
            return SandboxResult(
                success=False,
                execution_time_ms=0,
                exit_code=-1,
                error="Docker not available",
            )
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            return SandboxResult(
                success=False,
                execution_time_ms=execution_time,
                exit_code=-1,
                error=str(e),
            )
        finally:
            Path(script_path).unlink(missing_ok=True)

    def _build_script(
        self,
        code: str,
        function_name: str,
        args: tuple,
        kwargs: dict,
    ) -> str:
        """Build execution script for Docker."""
        args_json = json.dumps(args)
        kwargs_json = json.dumps(kwargs)

        return f'''
import json
import sys

# Generated function code
{code}

if __name__ == "__main__":
    try:
        args = json.loads({repr(args_json)})
        kwargs = json.loads({repr(kwargs_json)})
        result = {function_name}(*args, **kwargs)
        print(json.dumps(result))
    except Exception as e:
        print(f"Error: {{e}}", file=sys.stderr)
        sys.exit(1)
'''


class SandboxFactory:
    """Factory for creating appropriate sandbox based on risk level.

    Risk < 0.3: SubprocessSandbox (faster)
    Risk >= 0.3: DockerSandbox (more secure)
    """

    def __init__(self, docker_available: bool = True):
        """Initialize factory.

        Args:
            docker_available: Whether Docker is available on the system
        """
        self.docker_available = docker_available

    def get_sandbox(self, risk_score: float) -> SubprocessSandbox | DockerSandbox:
        """Get appropriate sandbox based on risk score.

        Args:
            risk_score: Code risk score from 0.0 to 1.0

        Returns:
            Subprocess sandbox for low risk, Docker for higher risk
        """
        if risk_score >= 0.3 and self.docker_available:
            return DockerSandbox()
        else:
            return SubprocessSandbox()


# Demo: Docker sandbox (only if Docker is available)
print("\nTesting Docker sandbox...")

docker_sandbox = DockerSandbox()
docker_available = docker_sandbox._check_docker_available()

if docker_available:
    docker_result = docker_sandbox.execute(
        test_code,
        "calculate_compound_interest",
        1000.0,
        0.05,
        10,
        compounds_per_year=12,
    )
    print(f"  Docker execution success: {docker_result.success}")
    print(f"  Result: {docker_result.result}")
    print(f"  Execution time: {docker_result.execution_time_ms:.2f}ms")
else:
    print("  Docker not available - skipping Docker sandbox demo")
    print("  (Subprocess sandbox will be used as fallback)")

# Demo SandboxFactory
print("\nSandboxFactory demo:")
factory = SandboxFactory(docker_available=docker_available)

low_risk_sandbox = factory.get_sandbox(0.1)
high_risk_sandbox = factory.get_sandbox(0.5)

print(f"  Risk 0.1 -> {type(low_risk_sandbox).__name__}")
print(f"  Risk 0.5 -> {type(high_risk_sandbox).__name__}")


# ============================================================================
# ITERATION 5: Runtime Tool Registration and Lifecycle
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 5: Runtime Tool Registration and Lifecycle")
print("=" * 70)


class ToolMetrics(BaseModel):
    """Performance metrics for a synthesized tool."""

    invocation_count: int = 0
    success_count: int = 0
    error_count: int = 0
    total_execution_time_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.invocation_count == 0:
            return 1.0
        return self.success_count / self.invocation_count

    @property
    def average_latency_ms(self) -> float:
        if self.invocation_count == 0:
            return 0.0
        return self.total_execution_time_ms / self.invocation_count


class SynthesizedTool(BaseModel):
    """A tool created at runtime."""

    tool_id: str = Field(description="Unique identifier")
    name: str = Field(description="Function name")
    spec: ToolSpec = Field(description="Original specification")
    source_code: str = Field(description="Generated Python code")
    sandbox_type: str = Field(default="subprocess", description="Sandbox to use")
    created_at: datetime = Field(default_factory=datetime.now)
    deprecated: bool = Field(default=False)
    deprecation_reason: str | None = Field(default=None)
    metrics: ToolMetrics = Field(default_factory=ToolMetrics)


class SynthesizedToolRegistry:
    """Registry for dynamically synthesized tools.

    Manages tool registration, lookup, and lifecycle.
    """

    def __init__(self):
        self._tools: dict[str, SynthesizedTool] = {}
        self._name_to_id: dict[str, str] = {}  # For lookup by name

    def register(self, tool: SynthesizedTool) -> str:
        """Register a synthesized tool.

        Args:
            tool: Tool to register

        Returns:
            Tool ID
        """
        self._tools[tool.tool_id] = tool
        self._name_to_id[tool.name] = tool.tool_id
        return tool.tool_id

    def unregister(self, tool_id: str) -> bool:
        """Unregister a tool.

        Args:
            tool_id: ID of tool to unregister

        Returns:
            True if tool was found and removed
        """
        if tool_id in self._tools:
            tool = self._tools[tool_id]
            del self._name_to_id[tool.name]
            del self._tools[tool_id]
            return True
        return False

    def get(self, tool_id: str) -> SynthesizedTool | None:
        """Get a tool by ID."""
        return self._tools.get(tool_id)

    def get_by_name(self, name: str) -> SynthesizedTool | None:
        """Get a tool by function name."""
        tool_id = self._name_to_id.get(name)
        return self._tools.get(tool_id) if tool_id else None

    def list_tools(self) -> list[SynthesizedTool]:
        """List all registered tools."""
        return list(self._tools.values())

    def get_strands_tool(self, tool_id: str) -> Callable | None:
        """Get a Strands-compatible @tool wrapper for a synthesized tool.

        Args:
            tool_id: ID of the synthesized tool

        Returns:
            Callable decorated with @tool, or None if not found
        """
        synth_tool = self.get(tool_id)
        if not synth_tool:
            return None

        # Create a wrapper that executes in sandbox
        sandbox = (
            DockerSandbox() if synth_tool.sandbox_type == "docker"
            else SubprocessSandbox()
        )

        def tool_wrapper(**kwargs) -> str:
            """Dynamically generated tool wrapper."""
            result = sandbox.execute(
                synth_tool.source_code,
                synth_tool.name,
                **kwargs,
            )

            # Update metrics
            synth_tool.metrics.invocation_count += 1
            synth_tool.metrics.total_execution_time_ms += result.execution_time_ms
            if result.success:
                synth_tool.metrics.success_count += 1
            else:
                synth_tool.metrics.error_count += 1

            if result.success:
                return json.dumps(result.result)
            else:
                return f"Error: {result.error}"

        # Set function metadata for Strands
        tool_wrapper.__name__ = synth_tool.name
        tool_wrapper.__doc__ = synth_tool.spec.description

        # Apply @tool decorator
        return tool(tool_wrapper)


class ToolLifecycleManager:
    """Manage tool lifecycle (creation, usage, deprecation)."""

    def __init__(self, registry: SynthesizedToolRegistry):
        self.registry = registry
        self.generator = CodeGenerator(model_alias="haiku")
        self.validator = CodeValidator()

    def create_tool(self, spec: ToolSpec) -> SynthesizedTool | None:
        """Create and register a new tool from specification.

        Args:
            spec: Tool specification

        Returns:
            SynthesizedTool if successful, None if validation fails
        """
        # Generate code
        generated = self.generator.generate(spec)

        # Validate
        validation = self.validator.validate(generated.source_code)
        if not validation.valid:
            print(f"Tool creation failed: {validation.errors}")
            return None

        # Determine sandbox type based on risk
        sandbox_type = "docker" if validation.risk_score >= 0.3 else "subprocess"

        # Create tool
        tool = SynthesizedTool(
            tool_id=str(uuid.uuid4()),
            name=spec.name,
            spec=spec,
            source_code=generated.source_code,
            sandbox_type=sandbox_type,
        )

        # Register
        self.registry.register(tool)
        return tool

    def deprecate_tool(self, tool_id: str, reason: str) -> bool:
        """Mark a tool as deprecated.

        Args:
            tool_id: Tool to deprecate
            reason: Why the tool is being deprecated

        Returns:
            True if tool was found and deprecated
        """
        tool = self.registry.get(tool_id)
        if tool:
            tool.deprecated = True
            tool.deprecation_reason = reason
            return True
        return False

    def garbage_collect(self, max_age_hours: int = 24) -> int:
        """Remove old unused tools.

        Args:
            max_age_hours: Maximum age for unused tools

        Returns:
            Number of tools removed
        """
        removed = 0
        cutoff = datetime.now() - timedelta(hours=max_age_hours)

        for tool in list(self.registry.list_tools()):
            # Remove if old and never used, or deprecated
            if tool.deprecated or (
                tool.created_at < cutoff and tool.metrics.invocation_count == 0
            ):
                self.registry.unregister(tool.tool_id)
                removed += 1

        return removed


# Demo: Tool registration and lifecycle
print("\nCreating tool registry and lifecycle manager...")

registry = SynthesizedToolRegistry()
lifecycle = ToolLifecycleManager(registry)

# Create a tool
print("\nCreating factorial tool...")
factorial_spec = ToolSpec(
    name="factorial",
    description="Calculate the factorial of a non-negative integer",
    parameters=[
        ParameterSpec(
            name="n",
            param_type="int",
            description="Non-negative integer to calculate factorial of",
            required=True,
        ),
    ],
    return_type="int",
    examples=["factorial(5) -> 120", "factorial(0) -> 1"],
)

factorial_tool = lifecycle.create_tool(factorial_spec)
if factorial_tool:
    print(f"  Created tool: {factorial_tool.name} (ID: {factorial_tool.tool_id[:8]}...)")
    print(f"  Sandbox type: {factorial_tool.sandbox_type}")

    # Get Strands-compatible tool and execute
    strands_tool = registry.get_strands_tool(factorial_tool.tool_id)
    if strands_tool:
        result = strands_tool(n=5)
        print(f"  Execution result: factorial(5) = {result}")
        print(f"  Tool metrics: {factorial_tool.metrics.invocation_count} invocations, "
              f"{factorial_tool.metrics.average_latency_ms:.2f}ms avg latency")

# List tools
print(f"\nRegistered tools: {len(registry.list_tools())}")
for t in registry.list_tools():
    print(f"  - {t.name}: {t.metrics.invocation_count} invocations")


# ============================================================================
# ITERATION 6: Capability-Based Permissions
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 6: Capability-Based Permissions")
print("=" * 70)


class SynthesizedToolCapability(str, Enum):
    """Capabilities that synthesized tools may request."""

    # Safe capabilities (allowed by default)
    CALCULATOR = "calculator"  # Math operations
    STRING_PROCESSING = "string_processing"  # String manipulation
    DATA_TRANSFORMATION = "data_transformation"  # JSON/dict operations
    DATE_TIME = "date_time"  # Date/time operations

    # Restricted capabilities (require explicit approval)
    FILE_READ = "file_read"  # Reading files
    FILE_WRITE = "file_write"  # Writing files
    NETWORK = "network"  # Network access
    CODE_EXECUTION = "code_execution"  # Dynamic code execution
    SYSTEM_COMMAND = "system_command"  # Shell commands


# Default capability allowlist for synthesized tools
ALLOWED_CAPABILITIES = {
    SynthesizedToolCapability.CALCULATOR,
    SynthesizedToolCapability.STRING_PROCESSING,
    SynthesizedToolCapability.DATA_TRANSFORMATION,
    SynthesizedToolCapability.DATE_TIME,
}

FORBIDDEN_CAPABILITIES = {
    SynthesizedToolCapability.FILE_READ,
    SynthesizedToolCapability.FILE_WRITE,
    SynthesizedToolCapability.NETWORK,
    SynthesizedToolCapability.CODE_EXECUTION,
    SynthesizedToolCapability.SYSTEM_COMMAND,
}


class CapabilityInferrer:
    """Infer required capabilities from code analysis."""

    # Patterns that indicate specific capabilities
    CAPABILITY_PATTERNS = {
        SynthesizedToolCapability.CALCULATOR: [
            r"\bmath\.", r"\+", r"-", r"\*", r"/", r"\*\*", r"sqrt", r"pow",
        ],
        SynthesizedToolCapability.STRING_PROCESSING: [
            r"\.split\(", r"\.join\(", r"\.replace\(", r"\.strip\(",
            r"\.upper\(", r"\.lower\(", r"\bre\.",
        ],
        SynthesizedToolCapability.DATA_TRANSFORMATION: [
            r"\bjson\.", r"\bdict\(", r"\blist\(", r"\.items\(",
            r"\.keys\(", r"\.values\(",
        ],
        SynthesizedToolCapability.DATE_TIME: [
            r"\bdatetime\.", r"\btime\.", r"\.strftime\(", r"\.strptime\(",
        ],
        SynthesizedToolCapability.FILE_READ: [
            r"\bopen\([^)]*['\"]r", r"\.read\(",
        ],
        SynthesizedToolCapability.FILE_WRITE: [
            r"\bopen\([^)]*['\"]w", r"\.write\(",
        ],
        SynthesizedToolCapability.NETWORK: [
            r"\brequests\.", r"\burllib\.", r"\bsocket\.", r"\bhttp\.",
        ],
        SynthesizedToolCapability.CODE_EXECUTION: [
            r"\beval\(", r"\bexec\(", r"\bcompile\(",
        ],
        SynthesizedToolCapability.SYSTEM_COMMAND: [
            r"\bos\.system\(", r"\bsubprocess\.", r"\bos\.popen\(",
        ],
    }

    def infer(self, source_code: str) -> set[SynthesizedToolCapability]:
        """Infer capabilities required by the code.

        Args:
            source_code: Python source code to analyze

        Returns:
            Set of inferred capabilities
        """
        capabilities = set()

        for capability, patterns in self.CAPABILITY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, source_code):
                    capabilities.add(capability)
                    break  # One match is enough for this capability

        return capabilities


class CapabilityEnforcer:
    """Enforce capability constraints on synthesized tools."""

    def __init__(
        self,
        allowed: set[SynthesizedToolCapability] | None = None,
        forbidden: set[SynthesizedToolCapability] | None = None,
    ):
        """Initialize with capability constraints.

        Args:
            allowed: Set of allowed capabilities (default: safe set)
            forbidden: Set of forbidden capabilities (default: dangerous set)
        """
        self.allowed = allowed or ALLOWED_CAPABILITIES
        self.forbidden = forbidden or FORBIDDEN_CAPABILITIES

    def check(
        self,
        source_code: str,
        inferrer: CapabilityInferrer | None = None,
    ) -> tuple[bool, set[SynthesizedToolCapability], list[str]]:
        """Check if code capabilities are allowed.

        Args:
            source_code: Code to check
            inferrer: Capability inferrer (created if not provided)

        Returns:
            Tuple of (allowed, inferred_capabilities, violations)
        """
        inferrer = inferrer or CapabilityInferrer()
        inferred = inferrer.infer(source_code)

        violations = []
        for cap in inferred:
            if cap in self.forbidden:
                violations.append(f"Forbidden capability: {cap.value}")
            elif cap not in self.allowed:
                violations.append(f"Unauthorized capability: {cap.value}")

        return len(violations) == 0, inferred, violations

    def wrap_with_enforcement(
        self,
        tool_func: Callable,
        required_caps: set[SynthesizedToolCapability],
    ) -> Callable:
        """Wrap a tool function with capability enforcement.

        Args:
            tool_func: Function to wrap
            required_caps: Capabilities required by the function

        Returns:
            Wrapped function that checks capabilities before execution
        """
        forbidden_caps = required_caps & self.forbidden
        if forbidden_caps:
            def blocked_func(*args, **kwargs):
                return f"Blocked: requires forbidden capabilities {forbidden_caps}"
            return blocked_func

        return tool_func


# Demo: Capability inference and enforcement
print("\nCapability inference and enforcement demo...")

inferrer = CapabilityInferrer()
enforcer = CapabilityEnforcer()

# Safe code
safe_code = '''
def calculate_area(length: float, width: float) -> float:
    """Calculate rectangle area."""
    return length * width
'''

safe_caps = inferrer.infer(safe_code)
safe_allowed, _, safe_violations = enforcer.check(safe_code)
print(f"\nSafe code (rectangle area):")
print(f"  Inferred capabilities: {[c.value for c in safe_caps]}")
print(f"  Allowed: {safe_allowed}")

# Code with forbidden capabilities
dangerous_code = '''
def read_config(path: str) -> dict:
    """Read configuration from file."""
    with open(path, 'r') as f:
        return json.loads(f.read())
'''

danger_caps = inferrer.infer(dangerous_code)
danger_allowed, _, danger_violations = enforcer.check(dangerous_code)
print(f"\nDangerous code (file read):")
print(f"  Inferred capabilities: {[c.value for c in danger_caps]}")
print(f"  Allowed: {danger_allowed}")
print(f"  Violations: {danger_violations}")

# Check the factorial tool
if factorial_tool:
    fact_caps = inferrer.infer(factorial_tool.source_code)
    fact_allowed, _, fact_violations = enforcer.check(factorial_tool.source_code)
    print(f"\nFactorial tool:")
    print(f"  Inferred capabilities: {[c.value for c in fact_caps]}")
    print(f"  Allowed: {fact_allowed}")


print("\n" + "=" * 70)
print("ITERATIONS 4-6 COMPLETE")
print("=" * 70)


# ============================================================================
# ITERATION 7: Multi-Step Synthesis Workflow
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 7: Multi-Step Synthesis Workflow")
print("=" * 70)


class SynthesisStep(str, Enum):
    """Steps in the synthesis pipeline."""

    GENERATE = "generate"
    VALIDATE_SYNTAX = "validate_syntax"
    SECURITY_SCAN = "security_scan"
    CAPABILITY_CHECK = "capability_check"
    TEST_EXECUTE = "test_execute"
    REGISTER = "register"


class StepResult(BaseModel):
    """Result of a single synthesis step."""

    step: str
    success: bool
    duration_ms: float
    error: str | None = None
    data: dict = Field(default_factory=dict)


class SynthesisResult(BaseModel):
    """Complete result of tool synthesis."""

    success: bool
    tool_id: str | None = None
    steps_completed: list[str] = Field(default_factory=list)
    step_results: dict[str, StepResult] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    total_time_ms: float = 0.0
    generated_code: str | None = None
    risk_score: float = 0.0


class TestCase(BaseModel):
    """Test case for verifying synthesized tools."""

    inputs: dict
    expected_output: Any
    description: str = ""


class SynthesisVerifier:
    """Verify synthesized tools work correctly."""

    def verify(
        self,
        code: str,
        function_name: str,
        test_cases: list[TestCase],
        sandbox: SubprocessSandbox | None = None,
    ) -> tuple[bool, list[str]]:
        """Run test cases and verify outputs.

        Args:
            code: Generated Python code
            function_name: Function to test
            test_cases: Test cases to run
            sandbox: Sandbox for execution

        Returns:
            Tuple of (all_passed, list of failure messages)
        """
        sandbox = sandbox or SubprocessSandbox()
        failures = []

        for i, test in enumerate(test_cases):
            result = sandbox.execute(code, function_name, **test.inputs)

            if not result.success:
                failures.append(f"Test {i+1}: Execution failed - {result.error}")
            elif result.result != test.expected_output:
                failures.append(
                    f"Test {i+1}: Expected {test.expected_output}, got {result.result}"
                )

        return len(failures) == 0, failures


class SynthesisWorkflow:
    """End-to-end tool synthesis with verification."""

    def __init__(
        self,
        registry: SynthesizedToolRegistry | None = None,
        model_alias: str = "haiku",
    ):
        self.registry = registry or SynthesizedToolRegistry()
        self.generator = CodeGenerator(model_alias=model_alias)
        self.validator = CodeValidator()
        self.capability_inferrer = CapabilityInferrer()
        self.capability_enforcer = CapabilityEnforcer()
        self.verifier = SynthesisVerifier()

    def synthesize(
        self,
        spec: ToolSpec,
        test_cases: list[TestCase] | None = None,
    ) -> SynthesisResult:
        """Synthesize a tool through the full pipeline.

        Pipeline: generate -> validate -> security_scan -> capability_check -> test -> register

        Args:
            spec: Tool specification
            test_cases: Optional test cases for verification

        Returns:
            SynthesisResult with detailed step outcomes
        """
        start_time = time.time()
        result = SynthesisResult(success=False)
        generated_code = ""

        # Step 1: Generate code
        step_result = self._run_step(
            SynthesisStep.GENERATE,
            lambda: self._generate(spec),
        )
        result.step_results[SynthesisStep.GENERATE] = step_result
        result.steps_completed.append(SynthesisStep.GENERATE)

        if not step_result.success:
            result.errors.append(step_result.error or "Generation failed")
            result.total_time_ms = (time.time() - start_time) * 1000
            return result

        generated_code = step_result.data.get("code", "")
        result.generated_code = generated_code

        # Step 2: Validate syntax
        step_result = self._run_step(
            SynthesisStep.VALIDATE_SYNTAX,
            lambda: self._validate_syntax(generated_code),
        )
        result.step_results[SynthesisStep.VALIDATE_SYNTAX] = step_result
        result.steps_completed.append(SynthesisStep.VALIDATE_SYNTAX)

        if not step_result.success:
            result.errors.append(step_result.error or "Syntax validation failed")
            result.total_time_ms = (time.time() - start_time) * 1000
            return result

        # Step 3: Security scan
        step_result = self._run_step(
            SynthesisStep.SECURITY_SCAN,
            lambda: self._security_scan(generated_code),
        )
        result.step_results[SynthesisStep.SECURITY_SCAN] = step_result
        result.steps_completed.append(SynthesisStep.SECURITY_SCAN)
        result.risk_score = step_result.data.get("risk_score", 0.0)

        if not step_result.success:
            result.errors.extend(step_result.data.get("errors", []))
            result.total_time_ms = (time.time() - start_time) * 1000
            return result

        # Step 4: Capability check
        step_result = self._run_step(
            SynthesisStep.CAPABILITY_CHECK,
            lambda: self._capability_check(generated_code),
        )
        result.step_results[SynthesisStep.CAPABILITY_CHECK] = step_result
        result.steps_completed.append(SynthesisStep.CAPABILITY_CHECK)

        if not step_result.success:
            result.errors.extend(step_result.data.get("violations", []))
            result.total_time_ms = (time.time() - start_time) * 1000
            return result

        # Step 5: Test execution (if test cases provided)
        if test_cases:
            step_result = self._run_step(
                SynthesisStep.TEST_EXECUTE,
                lambda: self._test_execute(generated_code, spec.name, test_cases),
            )
            result.step_results[SynthesisStep.TEST_EXECUTE] = step_result
            result.steps_completed.append(SynthesisStep.TEST_EXECUTE)

            if not step_result.success:
                result.errors.extend(step_result.data.get("failures", []))
                result.total_time_ms = (time.time() - start_time) * 1000
                return result

        # Step 6: Register tool
        step_result = self._run_step(
            SynthesisStep.REGISTER,
            lambda: self._register(spec, generated_code, result.risk_score),
        )
        result.step_results[SynthesisStep.REGISTER] = step_result
        result.steps_completed.append(SynthesisStep.REGISTER)

        if step_result.success:
            result.success = True
            result.tool_id = step_result.data.get("tool_id")

        result.total_time_ms = (time.time() - start_time) * 1000
        return result

    def _run_step(
        self,
        step: SynthesisStep,
        func: Callable[[], tuple[bool, dict]],
    ) -> StepResult:
        """Run a synthesis step with timing."""
        start = time.time()
        try:
            success, data = func()
            return StepResult(
                step=step,
                success=success,
                duration_ms=(time.time() - start) * 1000,
                data=data,
                error=data.get("error") if not success else None,
            )
        except Exception as e:
            return StepResult(
                step=step,
                success=False,
                duration_ms=(time.time() - start) * 1000,
                error=str(e),
            )

    def _generate(self, spec: ToolSpec) -> tuple[bool, dict]:
        """Generate code from spec."""
        generated = self.generator.generate(spec)
        if generated.source_code:
            return True, {"code": generated.source_code}
        return False, {"error": "No code generated"}

    def _validate_syntax(self, code: str) -> tuple[bool, dict]:
        """Validate code syntax."""
        validation = self.validator.validate(code)
        return validation.syntax_valid, {
            "errors": validation.errors if not validation.syntax_valid else []
        }

    def _security_scan(self, code: str) -> tuple[bool, dict]:
        """Scan for security issues."""
        validation = self.validator.validate(code)
        return validation.security_valid, {
            "risk_score": validation.risk_score,
            "errors": validation.errors,
            "warnings": validation.warnings,
        }

    def _capability_check(self, code: str) -> tuple[bool, dict]:
        """Check capabilities."""
        allowed, caps, violations = self.capability_enforcer.check(code)
        return allowed, {
            "capabilities": [c.value for c in caps],
            "violations": violations,
        }

    def _test_execute(
        self,
        code: str,
        function_name: str,
        test_cases: list[TestCase],
    ) -> tuple[bool, dict]:
        """Execute test cases."""
        passed, failures = self.verifier.verify(code, function_name, test_cases)
        return passed, {"failures": failures}

    def _register(
        self,
        spec: ToolSpec,
        code: str,
        risk_score: float,
    ) -> tuple[bool, dict]:
        """Register the tool."""
        tool = SynthesizedTool(
            tool_id=str(uuid.uuid4()),
            name=spec.name,
            spec=spec,
            source_code=code,
            sandbox_type="docker" if risk_score >= 0.3 else "subprocess",
        )
        self.registry.register(tool)
        return True, {"tool_id": tool.tool_id}


# Demo: Full synthesis workflow
print("\nRunning full synthesis workflow...")

workflow = SynthesisWorkflow()

# Create spec with test cases
gcd_spec = ToolSpec(
    name="gcd",
    description="Calculate the greatest common divisor of two integers using Euclidean algorithm",
    parameters=[
        ParameterSpec(name="a", param_type="int", description="First integer", required=True),
        ParameterSpec(name="b", param_type="int", description="Second integer", required=True),
    ],
    return_type="int",
    examples=["gcd(48, 18) -> 6", "gcd(100, 25) -> 25"],
)

test_cases = [
    TestCase(inputs={"a": 48, "b": 18}, expected_output=6, description="GCD of 48 and 18"),
    TestCase(inputs={"a": 100, "b": 25}, expected_output=25, description="GCD of 100 and 25"),
    TestCase(inputs={"a": 17, "b": 13}, expected_output=1, description="GCD of primes"),
]

synth_result = workflow.synthesize(gcd_spec, test_cases)

print(f"\nSynthesis result:")
print(f"  Success: {synth_result.success}")
print(f"  Tool ID: {synth_result.tool_id[:8] if synth_result.tool_id else 'N/A'}...")
print(f"  Steps completed: {synth_result.steps_completed}")
print(f"  Total time: {synth_result.total_time_ms:.2f}ms")
print(f"  Risk score: {synth_result.risk_score:.2f}")

if synth_result.errors:
    print(f"  Errors: {synth_result.errors}")

# Show step timings
print("\nStep timings:")
for step, step_result in synth_result.step_results.items():
    status = "OK" if step_result.success else "FAIL"
    print(f"  {step}: {step_result.duration_ms:.1f}ms [{status}]")


# ============================================================================
# ITERATION 8: Observability Integration (L21)
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 8: Observability Integration (L21)")
print("=" * 70)

# Note: Full OpenTelemetry integration requires the tracing infrastructure from L21
# This iteration shows the pattern for adding observability


class SynthesisSpanAttributes:
    """Standard span attributes for synthesis traces."""

    TOOL_SPEC_NAME = "synthesis.spec.name"
    TOOL_SPEC_PARAMS = "synthesis.spec.parameters"
    SANDBOX_TYPE = "synthesis.sandbox.type"
    RISK_SCORE = "synthesis.security.risk_score"
    GENERATION_TOKENS = "synthesis.generation.tokens"
    STEP_NAME = "synthesis.step.name"
    STEP_DURATION_MS = "synthesis.step.duration_ms"


class SynthesisMetrics:
    """Metrics collection for synthesis operations.

    In production, these would be Prometheus Counter/Histogram/Gauge.
    """

    def __init__(self):
        self.synthesis_total = 0
        self.synthesis_success = 0
        self.synthesis_errors = 0
        self.step_durations: dict[str, list[float]] = {}
        self.risk_scores: list[float] = []

    def record_synthesis(self, result: SynthesisResult):
        """Record a synthesis operation."""
        self.synthesis_total += 1
        if result.success:
            self.synthesis_success += 1
        else:
            self.synthesis_errors += 1

        self.risk_scores.append(result.risk_score)

        for step, step_result in result.step_results.items():
            if step not in self.step_durations:
                self.step_durations[step] = []
            self.step_durations[step].append(step_result.duration_ms)

    def get_summary(self) -> dict:
        """Get metrics summary."""
        return {
            "total_syntheses": self.synthesis_total,
            "success_rate": self.synthesis_success / max(1, self.synthesis_total),
            "avg_risk_score": sum(self.risk_scores) / max(1, len(self.risk_scores)),
            "step_avg_durations": {
                step: sum(durations) / len(durations)
                for step, durations in self.step_durations.items()
            },
        }


class TracedSynthesisWorkflow(SynthesisWorkflow):
    """Synthesis workflow with observability instrumentation.

    Adds:
    - Span creation for each step
    - Metrics collection
    - Structured logging
    """

    def __init__(
        self,
        registry: SynthesizedToolRegistry | None = None,
        model_alias: str = "haiku",
        metrics: SynthesisMetrics | None = None,
    ):
        super().__init__(registry, model_alias)
        self.metrics = metrics or SynthesisMetrics()

    def synthesize(
        self,
        spec: ToolSpec,
        test_cases: list[TestCase] | None = None,
    ) -> SynthesisResult:
        """Synthesize with tracing and metrics."""
        # In production: Create parent span
        # with tracer.start_as_current_span("synthesis.workflow") as span:
        #     span.set_attribute(SynthesisSpanAttributes.TOOL_SPEC_NAME, spec.name)

        print(f"  [TRACE] Starting synthesis for: {spec.name}")

        result = super().synthesize(spec, test_cases)

        # Record metrics
        self.metrics.record_synthesis(result)

        # Log completion
        status = "SUCCESS" if result.success else "FAILED"
        print(f"  [TRACE] Synthesis {status} in {result.total_time_ms:.1f}ms")

        return result


# Demo: Traced synthesis
print("\nRunning traced synthesis workflow...")

traced_metrics = SynthesisMetrics()
traced_workflow = TracedSynthesisWorkflow(metrics=traced_metrics)

# Run a few syntheses to collect metrics
specs_to_test = [
    ToolSpec(
        name="square",
        description="Calculate the square of a number",
        parameters=[ParameterSpec(name="x", param_type="float", description="Number to square")],
        return_type="float",
    ),
    ToolSpec(
        name="is_palindrome",
        description="Check if a string is a palindrome",
        parameters=[ParameterSpec(name="s", param_type="str", description="String to check")],
        return_type="bool",
    ),
]

for spec in specs_to_test:
    traced_workflow.synthesize(spec)

# Show metrics
print("\nMetrics summary:")
summary = traced_metrics.get_summary()
print(f"  Total syntheses: {summary['total_syntheses']}")
print(f"  Success rate: {summary['success_rate']:.1%}")
print(f"  Avg risk score: {summary['avg_risk_score']:.2f}")
print("  Step durations (avg):")
for step, avg in summary['step_avg_durations'].items():
    print(f"    {step}: {avg:.1f}ms")


# ============================================================================
# ITERATION 9: Recovery Integration (L23)
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 9: Recovery Integration (L23)")
print("=" * 70)


class SynthesisFailureType(str, Enum):
    """Types of synthesis failures for retry decisions."""

    TRANSIENT = "transient"  # Retry: LLM timeout, rate limit
    PERMANENT = "permanent"  # Don't retry: Invalid spec, security violation
    RETRYABLE = "retryable"  # Retry with backoff: Docker timeout, memory


class SynthesisFailureClassifier:
    """Classify synthesis failures for recovery decisions."""

    TRANSIENT_PATTERNS = [
        "timeout", "rate limit", "connection", "temporary",
    ]

    PERMANENT_PATTERNS = [
        "security", "forbidden", "invalid", "syntax error",
    ]

    def classify(self, error: str) -> SynthesisFailureType:
        """Classify a failure based on error message."""
        error_lower = error.lower()

        for pattern in self.PERMANENT_PATTERNS:
            if pattern in error_lower:
                return SynthesisFailureType.PERMANENT

        for pattern in self.TRANSIENT_PATTERNS:
            if pattern in error_lower:
                return SynthesisFailureType.TRANSIENT

        return SynthesisFailureType.RETRYABLE


@dataclass
class SynthesisRetryConfig:
    """Configuration for synthesis retry behavior."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0


class SynthesisFallback:
    """Fallback strategies when synthesis fails."""

    def __init__(self):
        self._template_cache: dict[str, str] = {}

    def get_template(self, spec: ToolSpec) -> str | None:
        """Try to find a template for the spec."""
        # Simple template matching by name pattern
        templates = {
            "calculator": '''
def {name}(a: float, b: float) -> float:
    """Simple calculator operation."""
    return a + b
''',
            "string": '''
def {name}(s: str) -> str:
    """Simple string operation."""
    return s.strip()
''',
        }

        for pattern, template in templates.items():
            if pattern in spec.name.lower() or pattern in spec.description.lower():
                return template.format(name=spec.name)
        return None


class ResilientSynthesizer:
    """Tool synthesizer with error recovery.

    Combines:
    - Retry with exponential backoff for transient failures
    - Fallback to templates for repeated failures
    - Failure classification for smart retry decisions
    """

    def __init__(
        self,
        workflow: SynthesisWorkflow | None = None,
        retry_config: SynthesisRetryConfig | None = None,
    ):
        self.workflow = workflow or SynthesisWorkflow()
        self.retry_config = retry_config or SynthesisRetryConfig()
        self.classifier = SynthesisFailureClassifier()
        self.fallback = SynthesisFallback()

    def synthesize(
        self,
        spec: ToolSpec,
        test_cases: list[TestCase] | None = None,
    ) -> SynthesisResult:
        """Synthesize with retry and fallback support.

        Strategy:
        1. Try full synthesis
        2. On transient failure: retry with backoff
        3. On repeated failure: try template fallback
        4. Return best effort result
        """
        last_result = None
        attempt = 0

        while attempt <= self.retry_config.max_retries:
            if attempt > 0:
                delay = self._calculate_delay(attempt - 1)
                print(f"  [RECOVERY] Retry {attempt}/{self.retry_config.max_retries} after {delay:.1f}s")
                time.sleep(delay)

            result = self.workflow.synthesize(spec, test_cases)
            last_result = result

            if result.success:
                return result

            # Classify failure
            error_msg = " ".join(result.errors) if result.errors else "Unknown error"
            failure_type = self.classifier.classify(error_msg)

            if failure_type == SynthesisFailureType.PERMANENT:
                print(f"  [RECOVERY] Permanent failure, not retrying: {error_msg}")
                break

            attempt += 1

        # Try fallback
        print("  [RECOVERY] Trying template fallback...")
        template = self.fallback.get_template(spec)
        if template:
            # Validate template
            validation = CodeValidator().validate(template)
            if validation.valid:
                # Register template-based tool
                tool = SynthesizedTool(
                    tool_id=str(uuid.uuid4()),
                    name=spec.name,
                    spec=spec,
                    source_code=template,
                    sandbox_type="subprocess",
                )
                self.workflow.registry.register(tool)
                return SynthesisResult(
                    success=True,
                    tool_id=tool.tool_id,
                    steps_completed=["fallback_template"],
                    generated_code=template,
                )

        return last_result or SynthesisResult(success=False, errors=["All attempts failed"])

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate retry delay with exponential backoff."""
        delay = self.retry_config.base_delay * (
            self.retry_config.exponential_base ** attempt
        )
        return min(delay, self.retry_config.max_delay)


# Demo: Resilient synthesis
print("\nDemonstrating resilient synthesis...")

resilient = ResilientSynthesizer()

# Test with a normal spec
normal_spec = ToolSpec(
    name="double",
    description="Double a number",
    parameters=[ParameterSpec(name="x", param_type="float", description="Number to double")],
    return_type="float",
)

print("\nSynthesizing 'double' function:")
result = resilient.synthesize(normal_spec)
print(f"  Success: {result.success}")
print(f"  Tool ID: {result.tool_id[:8] if result.tool_id else 'N/A'}...")

# Test failure classification
print("\nFailure classification examples:")
classifier = SynthesisFailureClassifier()
test_errors = [
    "Connection timeout after 30s",
    "Security violation: forbidden import",
    "Docker memory limit exceeded",
    "Rate limit exceeded",
]

for error in test_errors:
    failure_type = classifier.classify(error)
    print(f"  '{error}' -> {failure_type.value}")


print("\n" + "=" * 70)
print("ITERATIONS 7-9 COMPLETE")
print("=" * 70)


# ============================================================================
# ITERATION 10: Tool Versioning and A/B Testing
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 10: Tool Versioning and A/B Testing")
print("=" * 70)


class ToolVersion(BaseModel):
    """Version of a synthesized tool."""

    version_id: str
    tool_id: str
    version_number: int
    source_code: str
    created_at: datetime = Field(default_factory=datetime.now)
    status: str = "active"  # active, testing, deprecated
    metrics: ToolMetrics = Field(default_factory=ToolMetrics)


class ToolVersionManager:
    """Manage multiple versions of synthesized tools."""

    def __init__(self, registry: SynthesizedToolRegistry):
        self.registry = registry
        self._versions: dict[str, list[ToolVersion]] = {}  # tool_id -> versions
        self._active_versions: dict[str, str] = {}  # tool_id -> active version_id

    def create_version(
        self,
        tool_id: str,
        new_code: str,
        status: str = "testing",
    ) -> ToolVersion | None:
        """Create a new version of an existing tool.

        Args:
            tool_id: ID of the tool to version
            new_code: Updated source code
            status: Initial status (testing, active)

        Returns:
            New ToolVersion or None if tool not found
        """
        tool = self.registry.get(tool_id)
        if not tool:
            return None

        # Get next version number
        existing_versions = self._versions.get(tool_id, [])
        next_version = len(existing_versions) + 1

        version = ToolVersion(
            version_id=str(uuid.uuid4()),
            tool_id=tool_id,
            version_number=next_version,
            source_code=new_code,
            status=status,
        )

        if tool_id not in self._versions:
            self._versions[tool_id] = []
            # Store original as version 0
            original = ToolVersion(
                version_id=str(uuid.uuid4()),
                tool_id=tool_id,
                version_number=0,
                source_code=tool.source_code,
                status="active",
            )
            self._versions[tool_id].append(original)
            self._active_versions[tool_id] = original.version_id

        self._versions[tool_id].append(version)

        # If status is active, update the tool's source code
        if status == "active":
            tool.source_code = new_code
            self._active_versions[tool_id] = version.version_id

        return version

    def get_versions(self, tool_id: str) -> list[ToolVersion]:
        """Get all versions of a tool."""
        return self._versions.get(tool_id, [])

    def get_active_version(self, tool_id: str) -> ToolVersion | None:
        """Get the currently active version."""
        active_id = self._active_versions.get(tool_id)
        if not active_id:
            return None
        for v in self._versions.get(tool_id, []):
            if v.version_id == active_id:
                return v
        return None

    def rollback(self, tool_id: str, version_number: int) -> bool:
        """Rollback to a specific version.

        Args:
            tool_id: Tool to rollback
            version_number: Version number to restore

        Returns:
            True if rollback succeeded
        """
        tool = self.registry.get(tool_id)
        versions = self._versions.get(tool_id, [])

        for v in versions:
            if v.version_number == version_number:
                tool.source_code = v.source_code
                v.status = "active"
                self._active_versions[tool_id] = v.version_id
                return True
        return False

    def promote(self, tool_id: str, version_id: str) -> bool:
        """Promote a testing version to active."""
        tool = self.registry.get(tool_id)
        if not tool:
            return False

        versions = self._versions.get(tool_id, [])
        for v in versions:
            if v.version_id == version_id:
                # Demote current active
                current_active = self._active_versions.get(tool_id)
                for cv in versions:
                    if cv.version_id == current_active:
                        cv.status = "deprecated"
                # Promote new version
                v.status = "active"
                tool.source_code = v.source_code
                self._active_versions[tool_id] = v.version_id
                return True
        return False


class ABTest(BaseModel):
    """A/B test configuration."""

    test_id: str
    tool_id: str
    variant_a: str  # version_id
    variant_b: str  # version_id
    traffic_split: float = 0.5  # % going to variant B
    started_at: datetime = Field(default_factory=datetime.now)
    status: str = "running"  # running, concluded
    results: dict = Field(default_factory=dict)


class ABTestManager:
    """A/B testing for tool versions."""

    def __init__(self, version_manager: ToolVersionManager):
        self.version_manager = version_manager
        self._tests: dict[str, ABTest] = {}  # test_id -> ABTest
        self._tool_tests: dict[str, str] = {}  # tool_id -> active test_id
        self._outcomes: dict[str, list[dict]] = {}  # test_id -> outcomes

    def create_test(
        self,
        tool_id: str,
        variant_a_version: int,
        variant_b_version: int,
        traffic_split: float = 0.5,
    ) -> ABTest | None:
        """Create an A/B test between two versions."""
        versions = self.version_manager.get_versions(tool_id)
        version_a = version_b = None

        for v in versions:
            if v.version_number == variant_a_version:
                version_a = v
            if v.version_number == variant_b_version:
                version_b = v

        if not version_a or not version_b:
            return None

        test = ABTest(
            test_id=str(uuid.uuid4()),
            tool_id=tool_id,
            variant_a=version_a.version_id,
            variant_b=version_b.version_id,
            traffic_split=traffic_split,
        )

        self._tests[test.test_id] = test
        self._tool_tests[tool_id] = test.test_id
        self._outcomes[test.test_id] = []

        return test

    def get_variant(self, tool_id: str, request_id: str) -> str:
        """Get which variant to use for a request.

        Uses consistent hashing so same request_id always gets same variant.

        Returns:
            "A" or "B"
        """
        test_id = self._tool_tests.get(tool_id)
        if not test_id:
            return "A"  # No test running

        test = self._tests[test_id]

        # Consistent hash based on request_id
        hash_val = hash(request_id) % 100 / 100.0
        return "B" if hash_val < test.traffic_split else "A"

    def record_outcome(
        self,
        test_id: str,
        variant: str,
        success: bool,
        latency_ms: float,
    ):
        """Record the outcome of a tool invocation."""
        if test_id in self._outcomes:
            self._outcomes[test_id].append({
                "variant": variant,
                "success": success,
                "latency_ms": latency_ms,
                "timestamp": datetime.now().isoformat(),
            })

    def conclude_test(self, test_id: str) -> dict:
        """Conclude a test and determine winner."""
        test = self._tests.get(test_id)
        if not test:
            return {"error": "Test not found"}

        outcomes = self._outcomes.get(test_id, [])

        # Calculate metrics per variant
        results = {"A": {"count": 0, "successes": 0, "total_latency": 0.0},
                   "B": {"count": 0, "successes": 0, "total_latency": 0.0}}

        for outcome in outcomes:
            v = outcome["variant"]
            results[v]["count"] += 1
            if outcome["success"]:
                results[v]["successes"] += 1
            results[v]["total_latency"] += outcome["latency_ms"]

        for v in results:
            if results[v]["count"] > 0:
                results[v]["success_rate"] = results[v]["successes"] / results[v]["count"]
                results[v]["avg_latency"] = results[v]["total_latency"] / results[v]["count"]
            else:
                results[v]["success_rate"] = 0.0
                results[v]["avg_latency"] = 0.0

        # Determine winner (higher success rate wins, latency as tiebreaker)
        if results["A"]["success_rate"] > results["B"]["success_rate"]:
            winner = "A"
        elif results["B"]["success_rate"] > results["A"]["success_rate"]:
            winner = "B"
        elif results["A"]["avg_latency"] < results["B"]["avg_latency"]:
            winner = "A"
        else:
            winner = "B"

        test.status = "concluded"
        test.results = {"winner": winner, "metrics": results}

        # Clear active test
        if self._tool_tests.get(test.tool_id) == test_id:
            del self._tool_tests[test.tool_id]

        return test.results


# Demo: Versioning and A/B testing
print("\nDemonstrating tool versioning and A/B testing...")

# Use existing registry
version_registry = SynthesizedToolRegistry()
version_manager = ToolVersionManager(version_registry)

# Create a simple tool
simple_tool = SynthesizedTool(
    tool_id=str(uuid.uuid4()),
    name="add",
    spec=ToolSpec(
        name="add",
        description="Add two numbers",
        parameters=[
            ParameterSpec(name="a", param_type="float", description="First number"),
            ParameterSpec(name="b", param_type="float", description="Second number"),
        ],
    ),
    source_code="def add(a: float, b: float) -> float:\n    return a + b",
)
version_registry.register(simple_tool)

# Create a new version
improved_code = '''
def add(a: float, b: float) -> float:
    """Add two numbers with validation."""
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return float('nan')
    return float(a + b)
'''

v1 = version_manager.create_version(simple_tool.tool_id, improved_code, status="testing")
print(f"Created version {v1.version_number} (ID: {v1.version_id[:8]}...)")
print(f"Versions: {[v.version_number for v in version_manager.get_versions(simple_tool.tool_id)]}")

# A/B testing
ab_manager = ABTestManager(version_manager)
test = ab_manager.create_test(simple_tool.tool_id, 0, 1, traffic_split=0.5)

if test:
    print(f"\nA/B test created: {test.test_id[:8]}...")

    # Simulate requests
    import random
    for i in range(20):
        request_id = f"req_{i}"
        variant = ab_manager.get_variant(simple_tool.tool_id, request_id)
        success = random.random() > 0.1  # 90% success rate
        latency = random.uniform(40, 60)
        ab_manager.record_outcome(test.test_id, variant, success, latency)

    # Conclude test
    results = ab_manager.conclude_test(test.test_id)
    print(f"Test results: Winner={results['winner']}")
    print(f"  Variant A: {results['metrics']['A']['count']} calls, "
          f"{results['metrics']['A']['success_rate']:.1%} success")
    print(f"  Variant B: {results['metrics']['B']['count']} calls, "
          f"{results['metrics']['B']['success_rate']:.1%} success")


# ============================================================================
# ITERATION 11: Graphiti Persistence
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 11: Graphiti Persistence")
print("=" * 70)


class ToolGraphStore:
    """Persist synthesized tools to Graphiti graph memory.

    Enables:
    - Cross-session tool reuse
    - Semantic search for similar tools
    - Tool recommendations
    """

    def __init__(self, group_id: str = "synthesized_tools"):
        self.group_id = group_id
        self._local_cache: dict[str, SynthesizedTool] = {}

    async def save_tool(
        self,
        tool: SynthesizedTool,
        performance_summary: str = "",
    ) -> bool:
        """Save a tool to Graphiti.

        Args:
            tool: Tool to persist
            performance_summary: Optional performance notes

        Returns:
            True if saved successfully
        """
        # Build episode content
        episode_content = f"""
Synthesized Tool: {tool.name}
Description: {tool.spec.description}
Parameters: {', '.join(p.name for p in tool.spec.parameters)}
Return Type: {tool.spec.return_type}
Sandbox: {tool.sandbox_type}
Invocations: {tool.metrics.invocation_count}
Success Rate: {tool.metrics.success_rate:.1%}
{f'Performance: {performance_summary}' if performance_summary else ''}
"""

        # MCP integration happens via @tool functions below (persist_tool_to_graphiti)
        # which are invoked by Strands agents with MCP tools available.
        # This class manages local cache; see persist_tool_to_graphiti for real MCP calls.
        print(f"  [GRAPHITI] Saving tool '{tool.name}' to group '{self.group_id}'")
        self._local_cache[tool.tool_id] = tool
        return True

    async def search_similar(
        self,
        spec: ToolSpec,
        limit: int = 5,
    ) -> list[str]:
        """Search for similar existing tools.

        Args:
            spec: Specification to match
            limit: Max results

        Returns:
            List of tool descriptions that match
        """
        # MCP integration happens via @tool functions below (search_tools_in_graphiti)
        # which are invoked by Strands agents with MCP tools available.
        print(f"  [GRAPHITI] Searching for tools like '{spec.name}'")

        # Check local cache for demo
        matches = []
        for tool in self._local_cache.values():
            if (spec.name.lower() in tool.name.lower() or
                spec.description.lower() in tool.spec.description.lower()):
                matches.append(tool.name)
        return matches[:limit]

    async def get_tool(self, tool_id: str) -> SynthesizedTool | None:
        """Retrieve a tool by ID."""
        return self._local_cache.get(tool_id)


class ToolRecommender:
    """Recommend existing tools instead of synthesizing new ones."""

    def __init__(self, graph_store: ToolGraphStore):
        self.graph_store = graph_store

    async def recommend(
        self,
        spec: ToolSpec,
    ) -> list[dict]:
        """Get recommendations for a spec.

        Args:
            spec: Tool specification

        Returns:
            List of {name, similarity_score, reason}
        """
        matches = await self.graph_store.search_similar(spec, limit=3)

        recommendations = []
        for name in matches:
            recommendations.append({
                "name": name,
                "similarity_score": 0.8,  # Would be from vector similarity
                "reason": f"Similar function name/description to '{spec.name}'",
            })

        return recommendations


# Demo: Graphiti persistence (simulated)
print("\nDemonstrating Graphiti persistence (simulated)...")

import asyncio


async def demo_graphiti():
    graph_store = ToolGraphStore()
    recommender = ToolRecommender(graph_store)

    # Save a tool
    if factorial_tool:
        await graph_store.save_tool(factorial_tool, "Fast for n < 1000")

    # Search for similar
    similar_spec = ToolSpec(
        name="permutations",
        description="Calculate number of permutations",
        parameters=[ParameterSpec(name="n", param_type="int", description="Total items")],
    )

    matches = await graph_store.search_similar(similar_spec)
    print(f"  Found similar tools: {matches}")

    # Get recommendations
    recommendations = await recommender.recommend(similar_spec)
    print(f"  Recommendations: {recommendations}")


# Run async demo
asyncio.run(demo_graphiti())


# Graphiti integration tools for Strands Agent
@tool
def persist_tool_to_graphiti(tool_id: str, tool_name: str, description: str,
                              source_code: str, performance_notes: str = "") -> str:
    """Save a synthesized tool to Graphiti for future reuse.

    This tool should be used by an agent that has mcp__graphiti-memory tools available.
    The agent will call this, then invoke the MCP add_memory tool.

    Args:
        tool_id: ID of the tool to persist
        tool_name: Name of the synthesized tool
        description: What the tool does
        source_code: The generated Python source code
        performance_notes: Optional notes about tool performance

    Returns:
        Episode content for MCP add_memory call
    """
    episode_content = f"""Synthesized Tool: {tool_name}
Tool ID: {tool_id}
Description: {description}
Performance: {performance_notes}

Source Code:
```python
{source_code}
```

Use mcp__graphiti-memory__add_memory with:
- name: "synthesized_tool_{tool_name}"
- episode_body: <this content>
- group_id: "synthesized_tools"
- source: "text"
"""
    return episode_content


@tool
def search_tools_in_graphiti(query: str) -> str:
    """Search for previously synthesized tools in Graphiti.

    This tool prepares a search query. The agent should then call
    mcp__graphiti-memory__search_nodes with the query.

    Args:
        query: Search query describing the tool needed

    Returns:
        Instructions for MCP search call
    """
    return f"""To search for synthesized tools, use mcp__graphiti-memory__search_nodes with:
- query: "{query}"
- group_ids: ["synthesized_tools"]
- max_nodes: 5

Then parse the results to find matching tools."""


# ============================================================================
# ITERATION 12: Unified ToolSynthesizer Facade
# ============================================================================
print("\n" + "=" * 70)
print("ITERATION 12: Unified ToolSynthesizer Facade")
print("=" * 70)


class SynthesizerConfig(BaseModel):
    """Configuration for the unified synthesizer."""

    # Generation
    generator_model: str = "haiku"
    max_generation_retries: int = 3

    # Validation
    security_scan_enabled: bool = True
    max_risk_score: float = 0.3

    # Sandbox
    default_sandbox: str = "subprocess"  # subprocess or docker
    sandbox_timeout_seconds: float = 5.0

    # Recovery
    enable_retry: bool = True
    enable_fallback: bool = True

    # Versioning
    enable_versioning: bool = True
    max_versions_per_tool: int = 5

    # Persistence (Graphiti)
    enable_graphiti: bool = False
    graphiti_group_id: str = "synthesized_tools"

    # Observability
    enable_tracing: bool = True
    enable_metrics: bool = True


class ToolSynthesizer:
    """Unified facade for tool synthesis.

    Combines all synthesis capabilities:
    - Code generation and validation
    - Sandboxed execution
    - Tool registry and lifecycle
    - Versioning and A/B testing
    - Observability (tracing, metrics)
    - Error recovery (retry, fallback)
    - Graph persistence (Graphiti)
    """

    def __init__(self, config: SynthesizerConfig | None = None):
        """Initialize synthesizer with configuration.

        Args:
            config: Synthesizer configuration
        """
        self.config = config or SynthesizerConfig()

        # Core components
        self.registry = SynthesizedToolRegistry()
        self.generator = CodeGenerator(model_alias=self.config.generator_model)
        self.validator = CodeValidator()
        self.capability_inferrer = CapabilityInferrer()
        self.capability_enforcer = CapabilityEnforcer()

        # Workflow
        self.workflow = SynthesisWorkflow(
            registry=self.registry,
            model_alias=self.config.generator_model,
        )

        # Recovery
        if self.config.enable_retry:
            self.resilient = ResilientSynthesizer(workflow=self.workflow)

        # Versioning
        if self.config.enable_versioning:
            self.version_manager = ToolVersionManager(self.registry)
            self.ab_manager = ABTestManager(self.version_manager)

        # Observability
        if self.config.enable_metrics:
            self.metrics = SynthesisMetrics()

        # Persistence
        if self.config.enable_graphiti:
            self.graph_store = ToolGraphStore(self.config.graphiti_group_id)

    def synthesize(
        self,
        spec: ToolSpec,
        test_cases: list[TestCase] | None = None,
    ) -> SynthesisResult:
        """Synthesize a new tool from specification.

        This is the main entry point for tool synthesis.

        Args:
            spec: Tool specification
            test_cases: Optional test cases for verification

        Returns:
            SynthesisResult with tool ID if successful
        """
        # Use resilient synthesizer if retry enabled
        if self.config.enable_retry:
            result = self.resilient.synthesize(spec, test_cases)
        else:
            result = self.workflow.synthesize(spec, test_cases)

        # Record metrics
        if self.config.enable_metrics:
            self.metrics.record_synthesis(result)

        return result

    def synthesize_from_example(
        self,
        example: str,
        function_name: str,
    ) -> SynthesisResult:
        """Synthesize a tool from an example usage.

        Args:
            example: Example of how the tool should work
            function_name: Name for the synthesized function

        Returns:
            SynthesisResult
        """
        # Create a spec from the example
        spec = ToolSpec(
            name=function_name,
            description=f"Tool synthesized from example: {example}",
            parameters=[],  # Will be inferred
            examples=[example],
        )
        return self.synthesize(spec)

    def improve(
        self,
        tool_id: str,
        feedback: str,
    ) -> SynthesisResult:
        """Improve an existing tool based on feedback.

        Args:
            tool_id: ID of tool to improve
            feedback: What to improve

        Returns:
            SynthesisResult with new version
        """
        tool = self.registry.get(tool_id)
        if not tool:
            return SynthesisResult(success=False, errors=["Tool not found"])

        # Create improved spec
        improved_spec = ToolSpec(
            name=tool.name,
            description=f"{tool.spec.description}. Improvement: {feedback}",
            parameters=tool.spec.parameters,
            return_type=tool.spec.return_type,
        )

        # Synthesize improvement
        result = self.synthesize(improved_spec)

        # Create version if successful
        if result.success and self.config.enable_versioning:
            self.version_manager.create_version(
                tool_id,
                result.generated_code or "",
                status="testing",
            )

        return result

    def find_similar(self, spec: ToolSpec) -> list[SynthesizedTool]:
        """Find similar existing tools.

        Args:
            spec: Specification to match

        Returns:
            List of similar tools
        """
        matches = []
        for tool in self.registry.list_tools():
            # Simple similarity check
            if (spec.name.lower() in tool.name.lower() or
                any(word in tool.spec.description.lower()
                    for word in spec.description.lower().split())):
                matches.append(tool)
        return matches

    def get_tool(self, tool_id: str) -> SynthesizedTool | None:
        """Get a synthesized tool by ID."""
        return self.registry.get(tool_id)

    def get_strands_tool(self, tool_id: str) -> Callable | None:
        """Get a Strands-compatible tool wrapper."""
        return self.registry.get_strands_tool(tool_id)

    def get_metrics(self) -> dict:
        """Get synthesis metrics."""
        if self.config.enable_metrics:
            return self.metrics.get_summary()
        return {}

    def list_tools(self) -> list[SynthesizedTool]:
        """List all registered tools."""
        return self.registry.list_tools()


# Agent-callable tool for self-synthesis
@tool
def synthesize_new_tool(
    name: str,
    description: str,
    parameters_json: str,
    return_type: str = "str",
) -> str:
    """Create a new tool from natural language specification.

    Use this when you need a tool that doesn't exist.

    Args:
        name: Tool function name (valid Python identifier)
        description: What the tool should do
        parameters_json: JSON array of {name, type, description} for each parameter
        return_type: Expected return type

    Returns:
        Tool ID if successful, error message otherwise
    """
    try:
        params_data = json.loads(parameters_json)
        params = [
            ParameterSpec(
                name=p["name"],
                param_type=p.get("type", "str"),
                description=p.get("description", ""),
            )
            for p in params_data
        ]
    except (json.JSONDecodeError, KeyError) as e:
        return f"Error parsing parameters: {e}"

    spec = ToolSpec(
        name=name,
        description=description,
        parameters=params,
        return_type=return_type,
    )

    synthesizer = ToolSynthesizer()
    result = synthesizer.synthesize(spec)

    if result.success:
        return f"Tool created: {result.tool_id}"
    else:
        return f"Synthesis failed: {result.errors}"


# Demo: Unified ToolSynthesizer
print("\nDemonstrating unified ToolSynthesizer facade...")

config = SynthesizerConfig(
    generator_model="haiku",
    enable_retry=True,
    enable_versioning=True,
    enable_metrics=True,
)

synthesizer = ToolSynthesizer(config)

# Synthesize a tool
print("\n1. Synthesizing a 'cube' function...")
cube_spec = ToolSpec(
    name="cube",
    description="Calculate the cube of a number",
    parameters=[ParameterSpec(name="x", param_type="float", description="Number to cube")],
    return_type="float",
)

result = synthesizer.synthesize(cube_spec)
print(f"   Success: {result.success}")
print(f"   Tool ID: {result.tool_id[:8] if result.tool_id else 'N/A'}...")

# Find similar tools
print("\n2. Finding similar tools...")
similar = synthesizer.find_similar(ToolSpec(
    name="power",
    description="Calculate mathematical power",
    parameters=[],
))
print(f"   Similar tools: {[t.name for t in similar]}")

# Get metrics
print("\n3. Synthesis metrics:")
metrics = synthesizer.get_metrics()
print(f"   Total: {metrics.get('total_syntheses', 0)}")
print(f"   Success rate: {metrics.get('success_rate', 0):.1%}")

# List all tools
print("\n4. All registered tools:")
for tool in synthesizer.list_tools():
    print(f"   - {tool.name}: {tool.metrics.invocation_count} invocations")


print("\n" + "=" * 70)
print("LEVEL 24: TOOL SYNTHESIS COMPLETE")
print("=" * 70)
print("""
All 12 iterations implemented:

TIER 1: FOUNDATIONS (1-3)
  1. CodeGenerator - LLM-powered code synthesis
  2. CodeValidator + SecurityScanner - Multi-layer validation
  3. SubprocessSandbox - Basic process isolation

TIER 2: SAFETY (4-6)
  4. DockerSandbox - Maximum container isolation
  5. SynthesizedToolRegistry - Tool lifecycle management
  6. CapabilityInferrer/Enforcer - Permission control

TIER 3: INTEGRATION (7-9)
  7. SynthesisWorkflow - End-to-end pipeline
  8. TracedSynthesisWorkflow - Observability (spans, metrics)
  9. ResilientSynthesizer - Retry, fallback, failure classification

TIER 4: ADVANCED (10-12)
  10. ToolVersionManager + ABTestManager - Versioning and A/B testing
  11. ToolGraphStore - Graphiti persistence for cross-session reuse
  12. ToolSynthesizer - Unified facade with @tool for self-synthesis

Key patterns:
- Code generation: LLM generates Python; validate before execution
- Sandbox selection: risk < 0.3 = subprocess; risk >= 0.3 = Docker
- Security patterns: Block os, subprocess, eval, exec, open, __import__
- Capability inference: Analyze AST to determine required permissions
- Synthesis workflow: generate -> validate -> security_scan -> capability_check -> test -> register
- Recovery: Classify failures; fallback chain: full -> template -> cached
- Tool versioning: A/B test improvements; promote winners
- Graphiti persistence: Save successful tools for cross-session reuse
""")
