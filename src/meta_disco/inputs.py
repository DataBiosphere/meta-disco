"""Reading an input file: its envelope and its records (#615).

Below ``pipeline`` so that a reader of an input's envelope (reconcile, the run's
preflight, the input gate) need not import the classification pipeline.
``pipeline.load_classifiable_records`` builds on :func:`load_records`, adding the #376
exclusion.
"""

import json
from pathlib import Path

from .output_utils import leading_metadata


def load_records(input_path: Path) -> list:
    """Load the record list from an input file's envelope.

    Elements are not guaranteed to be dicts — an NDJSON line, or an entry inside the
    envelope's ``files``/``results`` list, may be any JSON value. (The envelope itself
    must be an object: a top-level JSON array is rejected by :func:`load_snapshot`.)
    Hence ``list``, not ``list[dict]``: this is the raw read, which the
    ``validate_metadata`` gate also takes (through :func:`load_snapshot`, beside the
    envelope) because it must see every element to report on it. Classification
    producers read ``pipeline.load_classifiable_records`` instead, which calls this and does
    narrow the element type.

    A ``.ndjson`` file is one record per line; otherwise a JSON object with a
    ``files`` (or legacy ``results``) list. The envelope handling is
    :func:`load_snapshot`'s, so it lives in one place.
    """
    return load_snapshot(input_path)[1]


def load_snapshot(input_path: Path) -> tuple[dict, list]:
    """Load an input file's ``metadata`` block and its record list in one parse.

    Same envelope handling and same errors as :func:`load_records`, which is this
    function's record half — a caller that also needs the envelope facts (which
    catalog a snapshot captured, when it was pulled) gets them without parsing a
    several-hundred-megabyte file a second time.

    The metadata block is ``{}`` for an ``.ndjson`` input, which carries no
    envelope, and for a JSON envelope that has no ``metadata`` key. Either loads
    here, but neither can start a classification run, which needs the envelope to
    name its repository (``record_keys.record_key``); the ``.ndjson`` twin the AnVIL
    downloader writes serves the reports, not the run.
    """
    with input_path.open() as f:
        if input_path.suffix == ".ndjson":
            return {}, [json.loads(line) for line in f if line.strip()]
        data = json.load(f)
    if not isinstance(data, dict):
        raise TypeError(f"Expected JSON object with 'results' or 'files' key, got {type(data).__name__}")
    metadata = data.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    # Check key presence explicitly rather than `results or files`: a present but
    # empty `results: []` is a valid empty corpus, not a missing key — the truthy
    # fallback would misreport it as "must contain a key".
    for key in ("results", "files"):
        if key in data:
            records = data[key]
            if not isinstance(records, list):
                raise TypeError(f"'{key}' must be a list of records, got {type(records).__name__}")
            return metadata, records
    raise ValueError("JSON object must contain a 'results' or 'files' key")


def load_envelope(input_path: Path) -> dict:
    """An input file's ``metadata`` block without parsing its records.

    Both writers put the block first — ``azul_manifest.write_input_files`` emits the
    literal ``{"metadata": `` before it, and the HPRC builder's ``json.dump`` keeps that
    insertion order — so it decodes off the file's head alone. That is a writer detail,
    not a contract, so a file laid out any other way falls back to :func:`load_snapshot`
    and gives the same answer at the cost of the full parse. Worth having because one
    caller is the run's preflight, whose process lives for the whole run: a full parse
    there leaves the corpus's heap resident beside the producers for its duration, for
    two keys' worth of information. The other is the catch-all producer, which refuses
    an input on this before it loads the records.

    ``{}`` for an ``.ndjson`` input, which carries no envelope, decided by suffix rather
    than by parsing every line to find that out.
    """
    if input_path.suffix == ".ndjson":
        return {}
    block = leading_metadata(input_path)
    return block if block is not None else load_snapshot(input_path)[0]
