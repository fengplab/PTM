// Download one PRIDE file over HTTPS and verify its size and MD5.
// RAW files always carry an MD5 (enforced by make_samplesheet.py); an SDRF
// without a PRIDE checksum is size-checked only.
// Raw files stay in the work directory (BeeGFS) for the later search step and
// are never published. SDRF files are published to NFS.
process DOWNLOAD_FILE {
    tag "${meta.accession}/${meta.file_name}"
    // UNVERIFIED: tag derived from the bioconda build string (pyteomics 4.7.5,
    // build pyh7e72e81_0, noarch); quay.io was unreachable from the build session.
    // The image is used only for its Python 3 interpreter (script is stdlib-only).
    container 'quay.io/biocontainers/pyteomics:4.7.5--pyh7e72e81_0'
    maxForks params.max_downloads

    publishDir "${params.publish_dir}/step1/${params.batch}/${meta.accession}/sdrf",
        mode: 'copy',
        saveAs: { fn -> (meta.kind == 'sdrf' && fn == meta.file_name) ? fn : null }

    input:
    tuple val(meta), val(url)

    output:
    tuple val(meta), path("${meta.file_name}"), emit: file
    path "versions.yml", emit: versions

    script:
    def md5_arg = meta.md5 ? "--md5 ${meta.md5}" : "--allow-no-md5"
    """
    download_verify.py \\
        --url '${url}' \\
        --out '${meta.file_name}' \\
        --size ${meta.size_bytes} \\
        ${md5_arg}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python3 -c 'import platform; print(platform.python_version())')
    END_VERSIONS
    """

    stub:
    """
    printf 'stub\\n' > '${meta.file_name}'
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: stub
    END_VERSIONS
    """
}
