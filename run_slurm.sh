#!/bin/bash
#SBATCH --job-name=ptm_nf
#SBATCH --partition=defq
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
# Nextflow head job. Submit from the project directory on BeeGFS:
#   sbatch run_slurm.sh <samplesheet.csv> <batch name>
# Each batch gets its own work directory (work_<batch>) so it can be removed
# on its own once its outputs are published to NFS.
set -euo pipefail
case "$PWD" in
    /home/bradlem9/isilon/*) echo "Launch from BeeGFS, not NFS (no file locking)" >&2; exit 1 ;;
esac
if [ "$#" -ne 2 ]; then
    echo "usage: sbatch run_slurm.sh <samplesheet.csv> <batch name>" >&2
    exit 1
fi
SAMPLESHEET="$1"
BATCH="$2"
module load nextflow singularity
export SINGULARITY_CACHEDIR="$PWD/.singularity/cache"
nextflow run main.nf -profile slurm \
    -params-file conf/params_cluster.yaml \
    --samplesheet "$SAMPLESHEET" \
    --batch "$BATCH" \
    -work-dir "work_${BATCH}" \
    -resume
