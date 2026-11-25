# Decisions

Scientific and infrastructure choices, with who made them and when.

## 2026-11-25 (user)

- **Datasets:** the 9 PRIDE accessions in `assets/accessions.txt`. Synapse
  datasets (syn10183279, syn21441875) excluded for now.
- **Modifications searched:**
  - deamidation (N, Q, +0.984016). Caveat: largely introduced during sample
    preparation; not interpretable as biology on its own.
  - methylation (+14.01565)
  - acetylation (+42.010565)
  - phosphoribosylation (+212.0086, C5H9O7P), residues S, R, E, D, K, C, H
  - ADP-ribosylation (+541.0611), residues S, R, E, D, K, C, H
  - Methylation: mono-, di- and tri-methyl on K and R (user, 2026-11-25).
  - Acetylation: K and protein N-termini (user, 2026-11-25).
  - TMT datasets: a lysine that is acetylated, di- or tri-methylated,
    ADP-ribosylated or phosphoribosylated has no free amine, so it cannot carry
    a TMT tag; monomethyl-K still can. The search must therefore not force TMT
    on every K. Approach to be set out in the search-step plan.
  - Trimethyl (+42.04695) and acetyl (+42.01057) differ by 0.036 Da. They can
    be told apart only with a tight precursor tolerance (about 36 ppm at
    1000 Da); results for these two are reported with that caveat.
- **Search engine:** MSFragger / FragPipe. Licence key supplied by the user at
  run time; never committed.
- **Targets:** `assets/target_genes.tsv`: the 8 phosphoribosyltransferases,
  NMNAT1-3, NADSYN1, NMRK1-2, and the de novo kynurenine pathway (TDO2, IDO1,
  IDO2, AFMID, KMO, KYNU, HAAO, ACMSD). Symbols are resolved against the
  search FASTA at run time; a symbol not found is an error.
  The search itself always uses the full human proteome (FDR validity).
- **Storage:** BeeGFS project dir and NFS publish dir in
  `conf/params_cluster.yaml`. 5 TB hard cap on BeeGFS across all projects.

## Step 0 results (from the user's run, 2026-11-25)

Source: `step0/dataset_summary.tsv`, `step0/plan/batch_plan.tsv` (user's laptop).

- 9 datasets, 1007 RAW files, 1.195 TB raw (decimal). All status OK, all `.raw`.
- PXD010603 alone is 0.632 TB raw (53% of the total).
- Batch plan used the default footprint factor 4.0, which is unmeasured.
