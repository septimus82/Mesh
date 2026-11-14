"""F6 (#422), in the fast tier: Mesh Studio never stages an AI proposal against a revision other than the one given.

A ``base_revision`` Studio no longer keeps (it keeps the last ``SNAPSHOTS_KEPT`` it was read at) is refused, as is one
that isn't a revision; nothing is staged, nothing reaches the person's inbox, the project is unchanged. Checked here on
the host itself, without a bridge; the same through the bridge, MCP and the CLI, with real revisions, eviction and
conflicts at acceptance, is in tests/test_studio_ai_base_revision.py (the integration tier, which every default run
includes; F13-A).
"""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

import pytest

from engine.studio_ai import SNAPSHOTS_KEPT, StudioAIHost

pytestmark = pytest.mark.fast
CHANGE = [{"op": "rename_entity", "entity_id": "warden", "name": "Guard"}]


class _Project:
    """The open project as far as staging a refused proposal looks: its revision and documents."""

    def __init__(self) -> None:
        self.revision = 0
        self.docs: dict[str, Any] = {"world": {}, "rooms": {}, "player": {}}

    def all_documents(self) -> dict[str, Any]:
        return self.docs


@pytest.fixture
def host() -> StudioAIHost:
    """Studio after SNAPSHOTS_KEPT + 1 reads, one per revision: revision 0, read first, is no longer kept."""
    inbox: list[str] = []
    studio = SimpleNamespace(project=_Project(), window=SimpleNamespace(), inbox=inbox,
                             on_ai_proposal=lambda proposal: inbox.append(proposal.title))
    ai = StudioAIHost(studio)
    for revision in range(SNAPSHOTS_KEPT + 1):
        studio.project.revision = revision
        studio.project.docs = {**studio.project.docs, "world": {"revision": revision}}
        ai._remember(revision, copy.deepcopy(studio.project.docs))  # (what a read keeps)
    return ai


def _nothing_staged(ai: StudioAIHost, docs: dict[str, Any]) -> None:
    assert ai.proposals == [] and ai.studio.inbox == [] and ai.project.all_documents() == docs


def test_an_evicted_revision_is_refused_with_the_current_one(host: StudioAIHost) -> None:
    docs = copy.deepcopy(host.project.all_documents())
    refused = host.stage_proposal_payload({"changes": CHANGE, "base_revision": 0})
    assert isinstance(refused, dict) and refused["ok"] is False and refused["reason"] == "base_revision_unavailable"
    assert refused["base_revision"] == 0 and refused["revision"] == SNAPSHOTS_KEPT
    assert f"revision {SNAPSHOTS_KEPT}" in refused["message"] and "Read the project again" in refused["message"]
    _nothing_staged(host, docs)


@pytest.mark.parametrize("given", [True, False, -1, SNAPSHOTS_KEPT + 1, "3", 2.0, [1]],
                         ids=["true", "false", "negative", "future", "a string", "a float", "a list"])
def test_something_that_isnt_a_revision_is_refused(host: StudioAIHost, given: Any) -> None:
    docs = copy.deepcopy(host.project.all_documents())  # (revisions 1.. are kept: a coerced value would find one)
    refused = host.stage_proposal_payload({"changes": CHANGE, "base_revision": given})
    assert isinstance(refused, dict) and refused["reason"] == "invalid_base_revision" and refused["base_revision"] == given
    assert refused["revision"] == SNAPSHOTS_KEPT and f"0 to {SNAPSHOTS_KEPT}" in refused["message"]
    _nothing_staged(host, docs)
