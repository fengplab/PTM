// PTM re-analysis of public PRIDE datasets.
// Step 1 (intake): download RAW and SDRF files with MD5 checks, read acquisition
// metadata from every RAW file, and summarise it per dataset. The per-dataset
// acquisition table decides the search parameters of the next step.

include { DOWNLOAD_FILE     } from './modules/local/download_file'
include { RAW_METADATA      } from './modules/local/raw_metadata'
include { SUMMARISE_RAWMETA } from './modules/local/summarise_rawmeta'

workflow {
    if (!params.samplesheet) {
        error "Missing --samplesheet (make it with bin/make_samplesheet.py)"
    }
    if (!params.publish_dir) {
        error "Missing --publish_dir (NFS publish directory; see conf/params_cluster.yaml)"
    }
    if (!params.batch) {
        error "Missing --batch (name of this download batch, e.g. pilot)"
    }

    ch_samplesheet = channel.value(file(params.samplesheet, checkIfExists: true))

    // Sample identity comes from the samplesheet rows, never from file globbing.
    ch_rows = channel.fromPath(params.samplesheet, checkIfExists: true)
        .splitCsv(header: true)
        .map { row ->
            ['accession', 'file_name', 'kind', 'size_bytes', 'url'].each { col ->
                if (!row[col]) {
                    error "Samplesheet row missing '${col}': ${row}"
                }
            }
            if (!(row.accession ==~ /PXD\d{6}/)) {
                error "Bad accession '${row.accession}'"
            }
            if (!(row.file_name ==~ /[A-Za-z0-9._+-]+/)) {
                error "Unsupported characters in file name '${row.file_name}'"
            }
            if (!(row.kind in ['raw', 'sdrf'])) {
                error "Unknown kind '${row.kind}' for ${row.file_name}"
            }
            if (row.kind == 'raw' && !(row.md5 ==~ /[0-9a-f]{32}/)) {
                error "RAW file ${row.file_name} has no valid MD5"
            }
            def stem = row.file_name.replaceFirst(/(?i)\.raw$/, '')
            def meta = [
                accession : row.accession,
                file_name : row.file_name,
                kind      : row.kind,
                size_bytes: row.size_bytes as Long,
                md5       : row.md5 ?: '',
                stem      : stem,
            ]
            [meta, row.url]
        }

    // Duplicate accession/file pairs would silently overwrite each other.
    ch_rows
        .map { meta, _url -> "${meta.accession}/${meta.file_name}" }
        .toList()
        .map { keys ->
            def dups = keys.countBy { k -> k }.findAll { _k, n -> n > 1 }.keySet()
            if (dups) {
                error "Duplicate samplesheet entries: ${dups}"
            }
            log.info "Samplesheet: ${keys.size()} files"
            keys.size()
        }

    DOWNLOAD_FILE(ch_rows)

    ch_raw = DOWNLOAD_FILE.out.file.filter { meta, _f -> meta.kind == 'raw' }
    RAW_METADATA(ch_raw)

    ch_json = RAW_METADATA.out.json
        .map { _meta, m, q -> [m, q] }
        .flatten()
        .collect()
    SUMMARISE_RAWMETA(ch_samplesheet, ch_json)

    DOWNLOAD_FILE.out.versions
        .mix(RAW_METADATA.out.versions, SUMMARISE_RAWMETA.out.versions)
        .map { f -> f.text.trim() + '\n' }
        .unique()
        .collectFile(
            name: 'software_versions.yml',
            storeDir: "${params.publish_dir}/step1/${params.batch}/pipeline_info",
            sort: true,
        )
}
