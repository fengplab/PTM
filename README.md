# PTM

Re-analysis of public PRIDE proteomics datasets (human brain tissue and
AD patient fibroblasts) for modifications on NAD/nucleotide
phosphoribosyltransferases and NAD-synthesis enzymes.

Modifications of interest: deamidation, methylation, acetylation,
phosphoribosylation (+212.0086 Da) and ADP-ribosylation (+541.0611 Da).
Search engine: MSFragger/FragPipe (licence key supplied by the user, never
committed).

## Status

| Step | What | State |
|-|-|-|
| 0 | `bin/fetch_manifest.py`, `bin/plan_batches.py`: list PRIDE files, plan download batches under the BeeGFS budget | written, unit-tested on mocked data; not yet run against PRIDE |
| 1+ | download, raw→mzML, search, FDR, target filtering, report (Nextflow) | not started; plan agreed, code pending |

## Layout

```
assets/          accession list and other small inputs
bin/             standalone scripts (also on PATH for Nextflow processes)
conf/            per-site params files (cluster paths live here, not in code)
modules/local/   Nextflow processes
docs/            notes and decisions
tests/           pytest tests on synthetic data
nextflow.config  parameters and the `slurm` profile
```

## Storage

- Launch Nextflow from the project directory on BeeGFS; `work/` and
  `.singularity/` live there. Never launch from NFS (`/home/bradlem9/isilon/`):
  it has no file locking.
- Raw files and intermediates are processed one batch at a time and deleted
  after the batch's results are published, to stay under the 5 TB BeeGFS cap.
- Final tables and reports are copied (not linked) to the NFS publish directory.

## Step 0 (laptop)

```bash
conda env create -f environment.yml   # once
conda activate ptm
python3 bin/fetch_manifest.py --accessions assets/accessions.txt --outdir step0
python3 bin/plan_batches.py --summary step0/dataset_summary.tsv \
    --manifest step0/manifest.tsv --available-tb <free TB> --outdir step0/plan
python3 -m pytest -q tests/
```

Standard-library Python 3 only. Downloads metadata only, no raw data.

## Step 1 (cluster): intake

Downloads the RAW and SDRF files of one batch with MD5 checks, reads
acquisition metadata from every RAW file (ThermoRawFileParser 1.4.5), and
publishes per-file and per-dataset acquisition tables to NFS.

```bash
# laptop or cluster: make the samplesheet for a batch
python3 bin/make_samplesheet.py --manifest step0/manifest.tsv \
    --summary step0/dataset_summary.tsv --accessions PXD059089 --out pilot.csv
# cluster, from the BeeGFS project directory
sbatch run_slurm.sh pilot.csv pilot
```

Outputs on NFS under `<publish_dir>/step1/<batch>/`: `rawfile_acquisition.tsv`,
`dataset_acquisition.tsv`, `<accession>/sdrf/`, `pipeline_info/`.
RAW files stay in `work_<batch>/` on BeeGFS until the batch is finished.

Stub test (no containers, no Slurm):

```bash
nextflow run main.nf -profile test -stub-run \
    --samplesheet tests/data/stub_samplesheet.csv --publish_dir /tmp/ptm_stub --batch stub
```
