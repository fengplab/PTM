// Collate per-file acquisition metadata into per-file and per-dataset tables.
// Fails if any RAW file in the samplesheet lacks metadata or has no MS2 scans.
process SUMMARISE_RAWMETA {
    tag "${params.batch}"
    // UNVERIFIED: see DOWNLOAD_FILE (same image, used for Python 3 only).
    container 'quay.io/biocontainers/pyteomics:4.7.5--pyh7e72e81_0'

    publishDir "${params.publish_dir}/step1/${params.batch}", mode: 'copy', pattern: '*.tsv'

    input:
    path samplesheet
    path jsons, stageAs: 'json/*'

    output:
    path "rawfile_acquisition.tsv", emit: per_file
    path "dataset_acquisition.tsv", emit: per_dataset
    path "versions.yml", emit: versions

    script:
    """
    summarise_rawmeta.py --samplesheet '${samplesheet}' --indir json --outdir .

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python3 -c 'import platform; print(platform.python_version())')
    END_VERSIONS
    """

    stub:
    """
    summarise_rawmeta.py --samplesheet '${samplesheet}' --indir json --outdir .
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: stub
    END_VERSIONS
    """
}
