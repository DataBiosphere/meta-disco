.PHONY: test lint classify download classify-bam classify-vcf classify-fastq classify-fasta classify-bed download-hprc validate-hprc clean help

help:
	@echo "meta-disco — AnVIL file metadata classification"
	@echo ""
	@echo "  make test            Run all tests"
	@echo "  make lint            Run ruff linter"
	@echo "  make classify        Run full classification pipeline (all file types, parallel)"
	@echo "  make download        Download fresh AnVIL metadata from API"
	@echo ""
	@echo "  make classify-bam    Classify BAM/CRAM files (network required)"
	@echo "  make classify-vcf    Classify VCF files (network required)"
	@echo "  make classify-fastq  Classify FASTQ files (network required)"
	@echo "  make classify-fasta  Classify FASTA files (network required)"
	@echo "  make classify-bed    Classify BED files"
	@echo ""
	@echo "  make download-hprc   Download HPRC catalogs for validation"
	@echo "  make validate-hprc   Validate classifications against HPRC catalogs"
	@echo ""
	@echo "  make clean           Remove cached .pyc files"

test:
	python -m pytest tests/ -v

lint:
	ruff check src/ scripts/ tests/

classify:
	python scripts/rerun_all_classifications.py

download:
	python scripts/download_anvil_metadata.py

classify-bam:
	python scripts/classify_bam_files.py -i data/anvil_files_metadata.json -w 4

classify-vcf:
	python scripts/classify_vcf_files.py -i data/anvil_files_metadata.json -w 4

classify-fastq:
	python scripts/classify_fastq_files.py -i data/anvil_files_metadata.json -w 4

classify-fasta:
	python scripts/classify_fasta_files.py -i data/anvil_files_metadata.json -w 4

classify-bed:
	python scripts/classify_bed_files.py --metadata data/anvil_files_metadata.json

download-hprc:
	python scripts/download_hprc_catalogs.py

validate-hprc:
	python scripts/validate_hprc_samples.py

clean:
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -type d -exec rm -rf {} +
