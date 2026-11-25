// Read acquisition metadata from one Thermo RAW file with ThermoRawFileParser 1.4.5.
// Flags checked against the v1.4.5 source (MainClass.cs):
//   main mode : -i input, -o output dir, -f 4 = no spectra output (default would
//               be MGF when -m is given), -m 0 = JSON metadata, -c metadata file
//   query     : -i input, -n scan range, -b output file (written as <stem>.json)
// Out-of-range scan numbers in -n only produce warnings (ProxiSpectrumReader.cs).
process RAW_METADATA {
    tag "${meta.accession}/${meta.file_name}"
    // UNVERIFIED: tag derived from the bioconda build string (thermorawfileparser
    // 1.4.5, build h05cac1d_1, noarch, package MD5 8a293809015a7760c8c4ab6dc5dde173);
    // quay.io was unreachable from the build session.
    container 'quay.io/biocontainers/thermorawfileparser:1.4.5--h05cac1d_1'

    input:
    tuple val(meta), path(raw)

    output:
    tuple val(meta), path("${meta.accession}__${meta.stem}.metadata.json"), path("${meta.accession}__${meta.stem}.query.json"), emit: json
    path "versions.yml", emit: versions

    script:
    def prefix = "${meta.accession}__${meta.stem}"
    """
    ThermoRawFileParser.sh -i '${raw}' -o . -f 4 -m 0 -c '${prefix}.metadata.json'
    ThermoRawFileParser.sh query -i '${raw}' -n '${params.query_scans}' -b '${prefix}.query.json'
    test -s '${prefix}.metadata.json'
    test -s '${prefix}.query.json'

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        thermorawfileparser: \$(ThermoRawFileParser.sh --version)
    END_VERSIONS
    """

    stub:
    def prefix = "${meta.accession}__${meta.stem}"
    """
    cat > '${prefix}.metadata.json' <<'EOF'
    {"InstrumentProperties":[{"accession":"MS:1000494","cvLabel":"MS","name":"Thermo Scientific instrument model","value":"Stub Orbitrap"}],
     "MsData":[{"accession":"PRIDE:0000481","cvLabel":"PRIDE","name":"Number of MS1 spectra","value":"10"},
               {"accession":"PRIDE:0000482","cvLabel":"PRIDE","name":"Number of MS2 spectra","value":"100"}],
     "ScanSettings":[{"accession":"MS:1000422","cvLabel":"MS","name":"beam-type collision-induced dissociation","value":"HCD"}]}
    EOF
    cat > '${prefix}.query.json' <<'EOF'
    [{"mzs":[],"intensities":[],"attributes":[{"accession":"MS:1000511","name":"ms level","value":"2"},
     {"accession":"MS:1000512","name":"filter string","value":"FTMS + c NSI d Full ms2 500.00@hcd38.00 [110.00-2000.00]"}]}]
    EOF
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        thermorawfileparser: stub
    END_VERSIONS
    """
}
