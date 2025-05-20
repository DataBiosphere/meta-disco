** Ollama Example: NHGRI AnVIL Title Summarizer**

This Ollama model summarizes the number of files associated with each unique datasets.title entry from a .tsv file exported from the NHGRI AnVIL platform.

Create the model from the Modelfile
```
$ ollama create nhgri-anvil-titles -f Modelfile
```
Run the model on NHGRI data table TSV file:
```
>>> ollama run nhgri-anvil-titles "$(cat ../findability-funk/anvil-manifest-3a7b7cb2-10be-5eb2-9c74-28f2662904ee.40bc3110-e5b2-5c64-92d2-99d0f02b28ed.tsv)" please summarize the datasets
... .title counts
Here is the summary of unique title counts:

Title: 1000 Genomes Project
Title: Alzheimer's Disease Neuroimaging Initiative (ADNI)
Title: Cancer Genome Atlas (TCGA)
Title: ClinVar
Title: Database of Genomic Variants (DGV)
Title: Encyclopedia of DNA Elements (ENCODE)
Title: Gene Expression Omnibus (GEO)
Title: Genotype-Tissue Expression (GTEx)
Title: International HapMap Project
Title: National Center for Biotechnology Information (NCBI) ClinVar
Title: The Cancer Genome Atlas (TCGA)

There are 10 unique titles.
```
