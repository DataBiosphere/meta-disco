.PHONY: test classify download fetch-bam fetch-vcf fetch-fastq fetch-fasta fetch-bed clean help

help:
	@echo "meta-disco — AnVIL file metadata classification"
	@echo ""
	@echo "  make test         Run all tests"
	@echo "  make classify     Run full classification pipeline (all file types, parallel)"
	@echo "  make download     Download fresh AnVIL metadata from API"
	@echo ""
	@echo "  make fetch-bam    Fetch BAM/CRAM headers from S3 (network required)"
	@echo "  make fetch-vcf    Fetch VCF headers from S3 (network required)"
	@echo "  make fetch-fastq  Fetch FASTQ headers from S3 (network required)"
	@echo "  make fetch-fasta  Fetch FASTA headers from S3 (network required)"
	@echo "  make fetch-bed    Fetch BED file data from S3 (network required)"
	@echo ""
	@echo "  make clean        Remove cached .pyc files"

test:
	python -m pytest tests/ -v

classify:
	python scripts/rerun_all_classifications.py

download:
	python scripts/download_anvil_metadata.py

fetch-bam:
	python scripts/fetch_bam_headers.py -i data/anvil_files_metadata.json -w 4

fetch-vcf:
	python scripts/fetch_vcf_headers.py -i data/anvil_files_metadata.json -w 4

fetch-fastq:
	python scripts/fetch_fastq_headers.py -i data/anvil_files_metadata.json -w 4

fetch-fasta:
	python scripts/fetch_fasta_headers.py -i data/anvil_files_metadata.json -w 4

fetch-bed:
	python scripts/fetch_bed_headers.py -i data/anvil_files_metadata.json -w 4

clean:
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -type d -exec rm -rf {} +
