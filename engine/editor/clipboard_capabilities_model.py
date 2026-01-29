"""Pure model for clipboard availability detection.

Centralizes the logic for determining when clipboard operations are safe.
This module is import-safe and has no side effects.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

# Environment variable names that indicate clipboard should be skipped
_CI_ENV_VARS = frozenset({
    "CI",
    "GITHUB_ACTIONS",
    "GITLAB_CI",
    "JENKINS_URL",
    "TRAVIS",
    "CIRCLECI",
    "BUILDKITE",
    "TF_BUILD",  # Azure Pipelines
})

_TEST_ENV_VARS = frozenset({
    "PYTEST_CURRENT_TEST",
})


def should_attempt_clipboard(
    env: Mapping[str, str],
    *,
    is_web: bool = False,
    is_headless: bool = False,
) -> bool:
    """Determine if clipboard operations should be attempted.

    Args:
        env: Environment variables mapping (typically os.environ).
        is_web: True if running in web/pygbag context.
        is_headless: True if running without a display.

    Returns:
        True if clipboard operations are safe to attempt, False otherwise.

    This function is pure and has no side effects. It centralizes all the
    logic for detecting when clipboard operations would hang or fail:
    - Web environments (pygbag) have no clipboard access
    - CI environments typically run headless
    - Test environments should not touch system clipboard
    - Headless environments have no display for tkinter
    """
    # Web has no clipboard access
    if is_web:
        return False

    # Headless has no display for tkinter
    if is_headless:
        return False

    # Check for CI environment variables
    for var in _CI_ENV_VARS:
        if env.get(var):
            return False

    # Check for test environment variables
    for var in _TEST_ENV_VARS:
        if env.get(var):
            return False

    return True


def is_ci_environment(env: Mapping[str, str]) -> bool:
    """Check if running in a CI environment.

    Args:
        env: Environment variables mapping.

    Returns:
        True if any CI environment variable is set.
    """
    return any(env.get(var) for var in _CI_ENV_VARS)


def is_test_environment(env: Mapping[str, str]) -> bool:
    """Check if running in a test environment.

    Args:
        env: Environment variables mapping.

    Returns:
        True if any test environment variable is set.
    """
    return any(env.get(var) for var in _TEST_ENV_VARS)
