.PHONY: test test-schema test-all lint lint-schema lint-all type format format-check classify classify-hprc classify-and-report download validate-metadata classify-bam classify-vcf classify-fastq classify-fasta classify-gfa classify-headers classify-bed coverage-report validation-report all-reports download-hprc validate-hprc clean help

help:
	@echo "meta-disco — AnVIL file metadata classification"
	@echo ""
	@echo "  make test               Run the classification (root) test suite"
	@echo "  make test-all           Run root + schema test suites (use before pushing)"
	@echo "  make lint               Run ruff on the root project"
	@echo "  make lint-all           Run ruff (root + schema) + pyright type check"
	@echo "  make type               Run pyright type checking on the root project"
	@echo "  make format             Reformat root project with ruff formatter"
	@echo "  make format-check       Check formatting without writing (CI)"
	@echo "  make classify           Run full classification pipeline (all file types, parallel)"
	@echo "  make classify-and-report Run classify + regenerate all reports"
	@echo "  make download           Download fresh AnVIL metadata from API"
	@echo "  make validate-metadata  Check a downloaded metadata file's shape before classifying"
	@echo ""
	@echo "  make classify-bam       Classify BAM/CRAM files (network required)"
	@echo "  make classify-vcf       Classify VCF files (network required)"
	@echo "  make classify-fastq     Classify FASTQ files (network required)"
	@echo "  make classify-fasta     Classify FASTA files (network required)"
	@echo "  make classify-gfa       Classify GFA/rGFA graph files (network required)"
	@echo "  make classify-bed       Classify BED files"
	@echo "  make classify-hprc      Classify HPRC catalog files (network required)"
	@echo "  make coverage-report    Generate coverage report from latest run"
	@echo "  make validation-report  Generate validation report against ground truth"
	@echo "  make all-reports        Generate all reports (coverage + validation)"
	@echo ""
	@echo "  make download-hprc      Download HPRC catalogs for validation"
	@echo "  make validate-hprc      Validate classifications against HPRC catalogs"
	@echo ""
	@echo "  make clean              Remove cached .pyc files"

test:
	uv run pytest tests/ -v

# Runs the schema tooling project's own suite (its own uv env, has linkml).
test-schema:
	$(MAKE) -C schema test

# Both projects — use this before pushing; the schema gate does not run under
# plain `make test` (the two are independent uv projects, #164).
test-all: test test-schema

lint:
	uv run ruff check src/ scripts/ tests/

lint-schema:
	$(MAKE) -C schema lint

# Root-project checks (ruff, then pyright) run before the separate schema/
# sub-make, so the pyright gate still runs even while lint-schema is red (#190).
lint-all: lint type lint-schema

# Pyright type checker (standard mode, separate from Ruff — issue #179). Resolves
# the meta_disco package + imports from the active uv venv. No path args: the
# checked paths come from [tool.pyright].include so they stay a single source
# of truth.
type:
	uv run pyright

# Ruff formatter (layout authority). `format` rewrites in place; `format-check`
# verifies without writing (used by CI, #180).
format:
	uv run ruff format src/ scripts/ tests/

format-check:
	uv run ruff format --check src/ scripts/ tests/

classify:
	uv run python scripts/rerun_all_classifications.py

classify-hprc:
	uv run python scripts/classify_hprc_files.py

classify-and-report: classify classify-hprc all-reports

download:
	uv run python scripts/download_anvil_metadata.py

# Pre-run gate: validate a downloaded metadata file against the input contract
# (issue #161). Non-zero exit on any shape violation. Run after `make download`.
validate-metadata:
	uv run python scripts/validate_metadata.py

classify-headers: classify-bam classify-vcf classify-fastq classify-fasta classify-gfa

classify-bam:
	uv run python scripts/classify_headers.py --type bam -i data/anvil/anvil_files_metadata.json -o output/anvil/bam_classifications.json -w 4

classify-vcf:
	uv run python scripts/classify_headers.py --type vcf -i data/anvil/anvil_files_metadata.json -o output/anvil/vcf_classifications.json -w 10

classify-fastq:
	uv run python scripts/classify_headers.py --type fastq -i data/anvil/anvil_files_metadata.json -o output/anvil/fastq_classifications.json -w 10

classify-fasta:
	uv run python scripts/classify_headers.py --type fasta -i data/anvil/anvil_files_metadata.json -o output/anvil/fasta_classifications.json -w 10

classify-gfa:
	uv run python scripts/classify_headers.py --type gfa -i data/anvil/anvil_files_metadata.json -o output/anvil/gfa_classifications.json -w 10

classify-bed:
	uv run python scripts/classify_bed_files.py --metadata data/anvil/anvil_files_metadata.json

coverage-report:
	uv run python scripts/generate_coverage_report.py

validation-report:
	uv run python scripts/generate_validation_report.py

all-reports: validate-hprc coverage-report validation-report

download-hprc:
	uv run python scripts/download_hprc_catalogs.py

validate-hprc:
	uv run python scripts/validate_against_hprc.py

clean:
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -type d -exec rm -rf {} +
