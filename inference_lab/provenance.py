"""Where a number came from. Every measurement and run result carries one of these."""

from __future__ import annotations

from enum import Enum


class Provenance(str, Enum):
    LIVE_MEASURED = "LIVE_MEASURED"  # measured on this machine by this app, during this run
    # Imported from a file whose schema and checksum are internally consistent. The checksum only shows the
    # file was not edited after export; anyone can write a record and compute a matching checksum, so this
    # says nothing about whether the numbers were really measured, where, or on what.
    IMPORTED = "IMPORTED"
    DEMO_SAMPLE = "DEMO_SAMPLE"  # bundled educational sample; never a claim about real hardware
    NOT_RUN = "NOT_RUN"  # the step did not execute (unsupported, skipped, or blocked)
    FAILED = "FAILED"  # the step executed and failed

    @classmethod
    def _missing_(cls, value: object) -> "Provenance | None":
        # Records written before the rename used "VERIFIED_IMPORTED"; read them as IMPORTED.
        return cls.IMPORTED if value == LEGACY_IMPORTED else None


LEGACY_IMPORTED = "VERIFIED_IMPORTED"

# Only numbers measured here may appear in the "measured results" part of a report.
# Imported records are shown in their own, clearly labelled section.
CLAIMABLE = {Provenance.LIVE_MEASURED}


def normalize(p: Provenance | str) -> str:
    return Provenance(p).value


def is_claimable(p: Provenance | str) -> bool:
    return Provenance(p) in CLAIMABLE


def is_imported(p: Provenance | str) -> bool:
    return Provenance(p) is Provenance.IMPORTED
