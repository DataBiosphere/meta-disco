"""A `FileTypeConfig` that classifies without fetching, for tests that drive `ClassifyPipeline`.

Beside `metadata_fixtures` rather than in it: that module builds *input* records and
stays free of the pipeline, while this one exists for the tests that run a pipeline end
to end — `test_pipeline` and the two published-comparison tests that pin what the
pipeline writes as `published.source`, with and without a catalog in the envelope.
"""

from dataclasses import replace

from meta_disco.pipeline import FileTypeConfig


def make_config(**overrides):
    """Create a FileTypeConfig with test defaults.

    The fetcher returns a string derived from the md5 instead of reading anything, and
    the classifier claims `data_modality: genomic` for every input.
    """
    return replace(
        FileTypeConfig(
            name="test",
            extensions=(".test",),
            fetcher=lambda evidence_dir, md5, **kw: f"header_for_{md5}",
            classifier=lambda raw_data, **kw: {"data_modality": {"value": "genomic"}},
        ),
        **overrides,
    )
