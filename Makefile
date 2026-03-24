.PHONY: test lint classify classify-and-report download classify-bam classify-vcf classify-fastq classify-fasta classify-headers classify-bed coverage-report validation-report all-reports download-hprc validate-hprc clean help

help:
	@echo "meta-disco — AnVIL file metadata classification"
	@echo ""
	@echo "  make test               Run all tests"
	@echo "  make lint               Run ruff linter"
	@echo "  make classify           Run full classification pipeline (all file types, parallel)"
	@echo "  make classify-and-report Run classify + regenerate all reports"
	@echo "  make download           Download fresh AnVIL metadata from API"
	@echo ""
	@echo "  make classify-bam       Classify BAM/CRAM files (network required)"
	@echo "  make classify-vcf       Classify VCF files (network required)"
	@echo "  make classify-fastq     Classify FASTQ files (network required)"
	@echo "  make classify-fasta     Classify FASTA files (network required)"
	@echo "  make classify-bed       Classify BED files"
	@echo "  make coverage-report    Generate coverage report from latest run"
	@echo "  make validation-report  Generate validation report against ground truth"
	@echo "  make all-reports        Generate all reports (coverage + validation)"
	@echo ""
	@echo "  make download-hprc      Download HPRC catalogs for validation"
	@echo "  make validate-hprc      Validate classifications against HPRC catalogs"
	@echo ""
	@echo "  make clean              Remove cached .pyc files"

test:
	python -m pytest tests/ -v

lint:
	ruff check src/ scripts/ tests/

classify:
	python scripts/rerun_all_classifications.py

classify-and-report: classify all-reports

download:
	python scripts/download_anvil_metadata.py

classify-headers: classify-bam classify-vcf classify-fastq classify-fasta

classify-bam:
	python scripts/classify_headers.py --type bam -i data/anvil/anvil_files_metadata.json -o output/anvil/bam_classifications.json -w 4

classify-vcf:
	python scripts/classify_headers.py --type vcf -i data/anvil/anvil_files_metadata.json -o output/anvil/vcf_classifications.json -w 10

classify-fastq:
	python scripts/classify_headers.py --type fastq -i data/anvil/anvil_files_metadata.json -o output/anvil/fastq_classifications.json -w 10

classify-fasta:
	python scripts/classify_headers.py --type fasta -i data/anvil/anvil_files_metadata.json -o output/anvil/fasta_classifications.json -w 10

classify-bed:
	python scripts/classify_bed_files.py --metadata data/anvil/anvil_files_metadata.json

coverage-report:
	python scripts/generate_coverage_report.py

validation-report:
	python scripts/generate_validation_report.py

all-reports: validate-hprc coverage-report validation-report

download-hprc:
	python scripts/download_hprc_catalogs.py

validate-hprc:
	python scripts/validate_against_hprc.py

clean:
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -type d -exec rm -rf {} +
