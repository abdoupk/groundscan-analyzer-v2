"""Exporting a record: the readable one and the lossless one.

Two artefacts, because they answer different questions. The HTML acceptance
record is for a reader -- every figure beside the limitation that qualifies
it, with the document embedded verbatim -- and the raw Document JSON is for a
machine, byte-for-byte what the engine emitted.

The HTML is produced by `groundscan-record`, not reimplemented here. That
package already renders multi-scan documents deterministically and holds
committed goldens for both shapes, so a second renderer over the same record
would be a second thing to keep in step with it.

Overwriting is refused unless asked for. An export is a file a reader may
already have sent to someone, and silently replacing one is not reversible.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from groundscan_record import write_record

from groundscan_analyzer import document as document_module

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

HTML_SUFFIX: str = ".html"
JSON_SUFFIX: str = ".json"


class ExportError(RuntimeError):
    """A record could not be written where it was asked for."""


def destination(directory: Path, stem: str, suffix: str) -> Path:
    """Name the file one export of this campaign would take.

    Args:
        directory: Where the record is going.
        stem: The campaign's own name, from the export or the folder.
        suffix: `.html` or `.json`.

    Returns:
        The path the record would occupy.
    """
    return directory / f"{stem}{suffix}"


def _guard(path: Path, *, force: bool) -> None:
    """Refuse to replace a record that is already there.

    Args:
        path: The file about to be written.
        force: Whether the reader asked to replace it.

    Raises:
        ExportError: Where the file exists and was not to be replaced.
    """
    if path.exists() and not force:
        message = f"{path} is already there; pass --force to replace it"
        raise ExportError(message)


def write_html(
    document: document_module.Document,
    directory: Path,
    stem: str,
    *,
    force: bool = False,
) -> Path:
    """Write the field acceptance record for a document.

    Args:
        document: The document to render.
        directory: Where to write it.
        stem: The campaign's own name.
        force: Whether to replace a record already there.

    Returns:
        The path written.
    """
    path = destination(directory, stem, HTML_SUFFIX)
    _guard(path, force=force)
    return write_record(document, path)


def write_json(
    document: document_module.Document,
    directory: Path,
    stem: str,
    *,
    force: bool = False,
) -> Path:
    """Write the document itself, byte-for-byte as the engine emitted it.

    Args:
        document: The document to serialise.
        directory: Where to write it.
        stem: The campaign's own name.
        force: Whether to replace a record already there.

    Returns:
        The path written.
    """
    path = destination(directory, stem, JSON_SUFFIX)
    _guard(path, force=force)
    path.write_text(document_module.dumps(document), encoding="utf-8")
    return path


def campaign_stem(paths: Sequence[Path]) -> str:
    """Name the campaign after what was read.

    One export names itself after its own file; a folder names the campaign
    after the folder, because no single file in it is the campaign.

    Args:
        paths: The frozen intake.

    Returns:
        The stem to write both records under.
    """
    if len(paths) == 1:
        return paths[0].stem
    parent = paths[0].parent
    return parent.name or "campaign"
