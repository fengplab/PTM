// Download one PRIDE file with pridepy 0.0.16 (FTP; HTTPS to ftp.pride.ebi.ac.uk is
// refused from the cluster), then verify it independently against the size and
// MD5 from the step 0 manifest before it becomes a task output.
// pridepy flags checked against the 0.0.16 source (pridepy.py, download/pride.py):
//   download-file-by-name -a accession -f exact file name -o output folder
//   --checksum-check : pridepy also validates against PRIDE's checksum file
//   default protocol ftp; on failure it falls back to aspera, s3, globus and
//   raises (non-zero exit) if every protocol fails.
// RAW files stay in the work directory (BeeGFS) for the later search step and
// are never published. SDRF files are published to NFS.
process DOWNLOAD_FILE {
    tag "${meta.accession}/${meta.file_name}"
    // UNVERIFIED: tag derived from the bioconda build string (pridepy 0.0.16,
    // build pyhdfd78af_0, noarch); quay.io was unreachable from the build session.
    container 'quay.io/biocontainers/pridepy:0.0.16--pyhdfd78af_0'
    maxForks params.max_downloads

    publishDir "${params.publish_dir}/step1/${params.batch}/${meta.accession}/sdrf",
        mode: 'copy',
        saveAs: { fn -> (meta.kind == 'sdrf' && fn == meta.file_name) ? fn : null }

    input:
    tuple val(meta), val(_url)

    output:
    tuple val(meta), path("${meta.file_name}"), emit: file
    path "versions.yml", emit: versions

    script:
    def md5_arg = meta.md5 ? "--md5 ${meta.md5}" : "--allow-no-md5"
    """
    pridepy download-file-by-name \\
        -a '${meta.accession}' \\
        -f '${meta.file_name}' \\
        -o dl \\
        --checksum-check

    verify_file.py --file 'dl/${meta.file_name}' --size ${meta.size_bytes} ${md5_arg}
    mv 'dl/${meta.file_name}' '${meta.file_name}'

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        pridepy: \$(pridepy --version | sed 's/.*version //')
        python: \$(python3 -c 'import platform; print(platform.python_version())')
    END_VERSIONS
    """

    stub:
    """
    printf 'stub\\n' > '${meta.file_name}'
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        pridepy: stub
    END_VERSIONS
    """
}
