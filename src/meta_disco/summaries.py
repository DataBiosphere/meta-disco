"""Summary printers for classification results."""


def _val(rec: dict, field: str):
    """Extract value from per-field or flat classification format."""
    cls = rec.get("classifications", {})
    if isinstance(cls, dict) and field in cls:
        v = cls[field]
        return v["value"] if isinstance(v, dict) and "value" in v else v
    v = rec.get(field)
    if isinstance(v, dict) and "value" in v:
        return v["value"]
    return v


def _print_field_table(title: str, counts: dict, width: int = 35):
    print(f"\n{title}:")
    for key, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {key:<{width}} {count:>5}")


def _print_sample_evidence(classifications: list[dict], fields: list[tuple[str, str]]):
    """Print sample evidence for first 3 files."""
    print("\n" + "-" * 70)
    print("SAMPLE EVIDENCE (first 3 files):")
    print("-" * 70)

    for c in classifications[:3]:
        print(f"\nFile: {c.get('file_name', 'unknown')}")
        for label, field in fields:
            val = _val(c, field)
            if val is not None:
                print(f"  {label}: {val}")

    print("=" * 70)


def print_bam_summary(classifications: list[dict]):
    """Print summary statistics of BAM/CRAM classifications."""
    print("\n" + "=" * 70)
    print("BAM/CRAM HEADER CLASSIFICATION SUMMARY")
    print("=" * 70)

    if not classifications:
        print("No classifications to summarize.")
        return

    modalities = {}
    references = {}
    platforms = {}
    aligned_count = 0
    unaligned_count = 0

    for c in classifications:
        mod = _val(c, "data_modality") or "unknown"
        modalities[mod] = modalities.get(mod, 0) + 1

        ref = _val(c, "reference_assembly") or "unknown"
        references[ref] = references.get(ref, 0) + 1

        plat = _val(c, "platform") or "unknown"
        platforms[plat] = platforms.get(plat, 0) + 1

        if _val(c, "is_aligned"):
            aligned_count += 1
        else:
            unaligned_count += 1

    print(f"\nTotal files classified: {len(classifications)}")
    print(f"  Aligned: {aligned_count}")
    print(f"  Unaligned: {unaligned_count}")

    _print_field_table("Data Modalities", modalities)
    _print_field_table("Reference Assemblies", references)
    _print_field_table("Platforms", platforms)

    _print_sample_evidence(classifications, [
        ("Modality", "data_modality"),
        ("Reference", "reference_assembly"),
        ("Platform", "platform"),
        ("Aligned", "is_aligned"),
    ])


def print_vcf_summary(classifications: list[dict]):
    """Print summary statistics of VCF classifications."""
    print("\n" + "=" * 70)
    print("VCF HEADER CLASSIFICATION SUMMARY")
    print("=" * 70)

    if not classifications:
        print("No classifications to summarize.")
        return

    modalities = {}
    data_types = {}
    references = {}

    for c in classifications:
        mod = _val(c, "data_modality") or "unknown"
        modalities[mod] = modalities.get(mod, 0) + 1

        dtype = _val(c, "data_type") or "unknown"
        data_types[dtype] = data_types.get(dtype, 0) + 1

        ref = _val(c, "reference_assembly") or "unknown"
        references[ref] = references.get(ref, 0) + 1

    print(f"\nTotal files classified: {len(classifications)}")

    _print_field_table("Data Modalities", modalities, width=40)
    _print_field_table("Data Types", data_types, width=40)
    _print_field_table("Reference Assemblies", references, width=40)

    _print_sample_evidence(classifications, [
        ("Modality", "data_modality"),
        ("Data Type", "data_type"),
        ("Reference", "reference_assembly"),
    ])


def print_fastq_summary(classifications: list[dict]):
    """Print summary statistics of FASTQ classifications."""
    print("\n" + "=" * 70)
    print("FASTQ HEADER CLASSIFICATION SUMMARY")
    print("=" * 70)

    if not classifications:
        print("No classifications to summarize.")
        return

    platforms = {}
    modalities = {}
    paired_count = 0
    instrument_models = {}
    archive_sources = {}

    for c in classifications:
        plat = _val(c, "platform") or "unknown"
        platforms[plat] = platforms.get(plat, 0) + 1

        mod = _val(c, "data_modality") or "unknown"
        modalities[mod] = modalities.get(mod, 0) + 1

        if _val(c, "is_paired_end"):
            paired_count += 1

        model = _val(c, "instrument_model")
        if model:
            instrument_models[model] = instrument_models.get(model, 0) + 1

        source = _val(c, "archive_source")
        if source:
            archive_sources[source] = archive_sources.get(source, 0) + 1

    print(f"\nTotal files classified: {len(classifications)}")
    print(f"  Paired-end detected: {paired_count}")

    _print_field_table("Platforms", platforms, width=30)
    _print_field_table("Data Modalities", modalities, width=30)

    if instrument_models:
        _print_field_table("Instrument Models (Illumina)", instrument_models, width=30)

    if archive_sources:
        _print_field_table("Archive Accessions", archive_sources, width=30)

    _print_sample_evidence(classifications, [
        ("Platform", "platform"),
        ("Modality", "data_modality"),
        ("Paired-end", "is_paired_end"),
        ("Instrument", "instrument_model"),
        ("Archive", "archive_accession"),
    ])
