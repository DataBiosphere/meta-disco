.PHONY: test test-network probe-tdr test-schema test-all lint lint-schema lint-all type format format-check classify classify-hprc classify-and-report download validate-metadata classify-bam classify-vcf classify-fastq classify-fasta classify-gfa classify-tar classify-headers classify-bed consistency-report coverage-report validation-report unprocessable-report published-comparison manifest-survey download-and-survey check-slot-map import-anvil-evidence check-published-map import-anvil-published seed-value-map review-queue corpus-diff all-reports download-hprc validate-hprc clean help

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
	@echo "  make download           Derive a deployment's input (DEPLOYMENT=prod|dev, INPUT_SOURCE=azul-compact|azul-verbatim|tdr-direct)"
	@echo "  make validate-metadata  Check a derived input's shape before classifying (DEPLOYMENT=prod|dev)"
	@echo "  make probe-tdr          Probe a TDR snapshot in BigQuery (PROJECT=... SNAPSHOT=... [TABLE=...] [BILLING_PROJECT=...])"
	@echo ""
	@echo "  make classify-bam       Classify BAM/CRAM files (network required)"
	@echo "  make classify-vcf       Classify VCF files (network required)"
	@echo "  make classify-fastq     Classify FASTQ files (network required)"
	@echo "  make classify-fasta     Classify FASTA files (network required)"
	@echo "  make classify-gfa       Classify GFA/rGFA graph files (network required)"
	@echo "  make classify-tar       Classify tar/tar.gz archives by inner format (network required)"
	@echo "  make classify-bed       Classify BED files"
	@echo "  make classify-hprc      Classify HPRC catalog files (network required)"
	@echo "  make coverage-report    Generate coverage report from latest run"
	@echo "  make manifest-survey    Survey what the downloaded manifests carry (offline)"
	@echo "  make download-and-survey Pull manifests, then survey what they carry"
	@echo "  make check-slot-map     Check the AnVIL slot map against the manifests on disk (offline)"
	@echo "  make import-anvil-evidence Import AnVIL submitter tables as a generation of evidence files"
	@echo "  make check-published-map Check the AnVIL published map against the manifests on disk (offline)"
	@echo "  make import-anvil-published Import AnVIL's published anvil_file columns as a generation of evidence files"
	@echo "  make seed-value-map     Append a seeded row to the value map for every evidence value with no row (offline)"
	@echo "  make review-queue       List every evidence value whose value-map row is not authored (offline)"
	@echo "  make unprocessable-report Report what a run could not classify, and why"
	@echo "  make published-comparison Compare a run against the values the repository publishes"
	@echo "  make validation-report  Generate validation report against ground truth"
	@echo "  make corpus-diff        Compare two corpus generations (snapshots by md5, runs by label)"
	@echo "  make all-reports        Generate every report (hprc, coverage, validation, consistency, unprocessable, published)"
	@echo ""
	@echo "  make download-hprc      Download HPRC catalogs for validation"
	@echo "  make validate-hprc      Validate classifications against HPRC catalogs"
	@echo ""
	@echo "  make test-network       Run the opt-in checks that call an external API"
	@echo "  make clean              Remove cached .pyc files"

test:
	uv run pytest tests/ -v

# The network-marked checks, which `make test` deliberately skips: they call a
# third-party API, so they are opt-in rather than part of the default gate.
# Today that is the Ensembl cross-check on REFERENCE_CONTIG_LENGTHS (#466) and the
# dev deployment's verbatim pull (#500), which writes under a temporary root.
test-network:
	uv run pytest tests/ -v -m network

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

# The input-contract gate is a real prerequisite, not a documented habit (#376):
# `make classify` fails before the multi-hour run if any record violates the input
# contract — the WHOLE contract, including fields the classifier never reads, not only
# the ones that would make a record unclassifiable. So this refuses to start on any
# drifted corpus, which is stricter than the run itself needs (#161 deliberately lets a
# record bad on, say, drs_uri still classify).
#
# It is not quite a superset of the #376 exclusion, so it does not name every record the
# run would exclude: the contract's generated validator anchors with `$`, which matches
# before a trailing newline, while exclusions.MD5_RE anchors with `\Z`. A file_md5sum of
# "<32 hex>\n" therefore passes this gate and is still excluded from classification. That
# record is named in the run's excluded_files.json instead.
#
# A classification run is not given a deployment yet (#480): it reads prod's input, so
# its gate checks prod's input whatever DEPLOYMENT says, rather than depending on the
# validate-metadata target, which follows DEPLOYMENT.
classify:
	uv run python scripts/validate_metadata.py --deployment prod
	uv run python scripts/rerun_all_classifications.py

classify-hprc:
	uv run python scripts/classify_hprc_files.py

classify-and-report: classify classify-hprc all-reports

# Which deployment's input to derive, and how (#500). The deployment
# (src/meta_disco/deployments.py) names the Azul service, the catalog, the root the
# input is written under (data/anvil/<deployment>/) and each dataset's TDR snapshot;
# the catalog is named there explicitly (#335, #368), because the service default
# advances without notice. INPUT_SOURCE is how the records are derived: azul-compact
# (the default; both manifests, the compact join), azul-verbatim (the verbatim manifest
# only) or tdr-direct (the snapshots read in place from BigQuery, nothing downloaded).
# An unknown value of either is refused by the script before any request, query or
# write of its own; with INPUT_SOURCE=tdr-direct, `uv run --extra tdr` syncs that
# extra into the environment first.
# tdr-direct runs with `--extra tdr`, the way probe-tdr does, and takes its identity
# from the environment: see meta_disco.tdr. Unset, each is the script's own default
# (prod, azul-compact), so the defaults have one spelling.
download:
	$(if $(CATALOG),$(error CATALOG is retired (#500): the deployment names its catalog, so pass DEPLOYMENT=prod or DEPLOYMENT=dev))
	uv run $(if $(filter tdr-direct,$(INPUT_SOURCE)),--extra tdr) python scripts/download_anvil_manifest.py $(if $(DEPLOYMENT),--deployment $(DEPLOYMENT)) $(if $(INPUT_SOURCE),--input-source $(INPUT_SOURCE)) $(if $(BILLING_PROJECT),--billing-project $(BILLING_PROJECT))

# Probe a TDR snapshot through the BigQuery layer (#498): list its tables, count
# each, stream one (TABLE; the script's default is anvil_file) and time it.
# `--extra tdr` syncs the client library in for this run, so a plain `uv sync`
# in between cannot strand the target. BILLING_PROJECT is for a laptop whose
# ADC has no default project; inside Terra the environment's own is expected to
# be the workspace project (the live probe on #478 confirms). Identity:
# see meta_disco.tdr.
probe-tdr:
	uv run --extra tdr python scripts/probe_tdr_snapshot.py --project $(PROJECT) --snapshot $(SNAPSHOT) $(if $(TABLE),--table $(TABLE)) $(if $(BILLING_PROJECT),--billing-project $(BILLING_PROJECT))

# Pre-run gate: validate a downloaded metadata file against the input contract
# (issue #161). Non-zero exit on any shape violation. Run it directly after
# `make download`; `make classify` also runs it as a prerequisite (#376), so a long
# run cannot start on a corpus that violates the contract.
validate-metadata:
	uv run python scripts/validate_metadata.py $(if $(DEPLOYMENT),--deployment $(DEPLOYMENT))

# `make classify-headers` runs the six header types into ONE dated partials folder
# (a shared RUN_DIR). A standalone `make classify-<type>` run instead lands in its
# own fresh output/anvil/partials/<timestamp>/ folder. The reports' find_latest_run
# selects only digit-prefixed run dirs, so the letter-prefixed partials/ folder is
# skipped (see output_utils.find_latest_run).
# The per-type targets omit -o so classify_headers.py derives
# <type>_classifications.json; pass RUN_DIR=... to a per-type target (e.g.
# `make classify-bam RUN_DIR=...`) to place its output, or leave it unset for the
# dated-partials default. classify-headers sets its own shared RUN_DIR, so a
# RUN_DIR passed to classify-headers itself is overridden.
# RUN_DIR_ARG expands to nothing when RUN_DIR is unset (standalone run).
RUN_DIR_ARG = $(if $(RUN_DIR),--run-dir $(RUN_DIR))

classify-headers:
	$(MAKE) classify-bam classify-vcf classify-fastq classify-fasta classify-gfa classify-tar \
		RUN_DIR="output/anvil/partials/$$(date +%Y%m%d_%H%M%S)"

classify-bam:
	uv run python scripts/classify_headers.py --type bam $(RUN_DIR_ARG) -w 4

classify-vcf:
	uv run python scripts/classify_headers.py --type vcf $(RUN_DIR_ARG) -w 10

classify-fastq:
	uv run python scripts/classify_headers.py --type fastq $(RUN_DIR_ARG) -w 10

classify-fasta:
	uv run python scripts/classify_headers.py --type fasta $(RUN_DIR_ARG) -w 10

classify-gfa:
	uv run python scripts/classify_headers.py --type gfa $(RUN_DIR_ARG) -w 10

classify-tar:
	uv run python scripts/classify_headers.py --type tar $(RUN_DIR_ARG) -w 10

classify-bed:
	uv run python scripts/classify_headers.py --type bed $(RUN_DIR_ARG) -w 10

consistency-report:
	uv run python scripts/check_consistency.py

# What the run could not classify, and why (#376): checksum-less files excluded from
# classification, input-contract violations, and content that could not be read.
unprocessable-report:
	uv run python scripts/generate_unprocessable_report.py

coverage-report:
	uv run python scripts/generate_coverage_report.py

# What the downloaded manifests actually carry (#384): compact column coverage,
# the verbatim entity census, file-to-donor reach each way, and which datasets can
# support #369 / #336 / #361. Offline — it reads what `make download` left on disk,
# so it is regenerated after a manifest pull, not after a classification run, which
# is why it is not part of all-reports.
manifest-survey:
	uv run python scripts/generate_manifest_survey.py

# The survey reads what `make download` leaves on disk, so the two belong
# together after a catalog refresh — the same shape as classify-and-report. The
# survey reads prod's compact and verbatim manifests (#500 does not give it a
# deployment), so only a prod azul-compact download is surveyed; any other choice
# is refused before the download rather than surveying manifests it did not pull.
download-and-survey:
	$(if $(filter-out prod,$(DEPLOYMENT)),$(error download-and-survey surveys prod's manifests only; drop DEPLOYMENT=$(DEPLOYMENT)))
	$(if $(filter-out azul-compact,$(INPUT_SOURCE)),$(error download-and-survey needs both manifests, which only INPUT_SOURCE=azul-compact pulls))
	$(MAKE) download manifest-survey

# The AnVIL slot map (#369): check it against the manifests on disk, or import
# every dataset it names as one new generation of evidence files under
# data/source_evidence/anvil/. Offline.
check-slot-map:
	uv run python scripts/import_anvil_evidence.py --check

import-anvil-evidence:
	uv run python scripts/import_anvil_evidence.py $(ARGS)

# The AnVIL published map (#497): the harmonized anvil_file columns — what AnVIL
# itself publishes — through the same importer, as generations under
# data/source_evidence/anvil_published/. Offline; reads the verbatim manifest.
check-published-map:
	uv run python scripts/import_anvil_evidence.py --check --published

import-anvil-published:
	uv run python scripts/import_anvil_evidence.py --published $(ARGS)

# The value translation table (#414; src/meta_disco/value_map.py). Seed it from the
# current evidence, or list its review queue; `ARGS="--dataset X"` scans one dataset.
# Both offline.
seed-value-map:
	uv run python scripts/value_map.py $(ARGS) seed

review-queue:
	uv run python scripts/value_map.py $(ARGS) queue

# Depends on validate-hprc because HPRC is now its only source (#424 moved the AnVIL
# comparison to published-comparison). Its input, output/hprc/hprc_validation_results.json,
# is generated and gitignored, so without this prerequisite a standalone run on a fresh
# checkout finds no sources and exits 1 — which it did not before, when the AnVIL branch
# keyed off the always-present downloaded metadata.
validation-report: validate-hprc
	uv run python scripts/generate_validation_report.py

# This run's inferred values beside the ones the repository publishes (#424): what each
# side has per file, and what the repository should do about the difference. Offline —
# the pipeline carries the published values into each record, so it reads only the run's
# own output.
published-comparison:
	uv run python scripts/generate_published_comparison.py

# Compare two corpus generations: input snapshots file-by-file by md5, and run
# outputs by label, splitting each coverage delta into corpus loss / corpus gain /
# label change so a catalog migration is not mistaken for classifier drift (#335).
# Defaults compare the archived anvil14 generation with the latest run; pass other
# snapshots or runs through ARGS, e.g.
# `make corpus-diff ARGS="--new-run output/anvil/20260904_010319"`.
corpus-diff:
	uv run python scripts/compare_corpus.py $(ARGS)

all-reports: validate-hprc coverage-report validation-report consistency-report unprocessable-report published-comparison

download-hprc:
	uv run python scripts/download_hprc_catalogs.py

validate-hprc:
	uv run python scripts/validate_against_hprc.py

clean:
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -type d -exec rm -rf {} +
