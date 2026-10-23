"""Where a number came from. Every measurement and run result carries one of these."""

from __future__ import annotations

from enum import Enum


class Provenance(str, Enum):
    LIVE_MEASURED = "LIVE_MEASURED"  # measured on this machine by this app, during this run
    VERIFIED_IMPORTED = "VERIFIED_IMPORTED"  # imported file whose schema and checksum were verified
    DEMO_SAMPLE = "DEMO_SAMPLE"  # bundled educational sample; never a claim about real hardware
    NOT_RUN = "NOT_RUN"  # the step did not execute (unsupported, skipped, or blocked)
    FAILED = "FAILED"  # the step executed and failed


# Only these may appear in the "measured results" part of a report.
CLAIMABLE = {Provenance.LIVE_MEASURED, Provenance.VERIFIED_IMPORTED}


def is_claimable(p: Provenance | str) -> bool:
    return Provenance(p) in CLAIMABLE
