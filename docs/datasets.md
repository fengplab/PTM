# Datasets

What each dataset contains, taken from its PRIDE project record
(`step0/json/<accession>.project.json`) and `step0/dataset_summary.tsv`.
Acquisition settings stated here are the submitters' descriptions; the
pipeline measures them from every RAW file in step 1
(`dataset_acquisition.tsv`), and the measured values win.

| Accession | Tissue | Labelling | Instrument | RAW files | Raw size |
|-|-|-|-|-|-|
| PXD015690 | DLPFC | TMT | Orbitrap Fusion Lumos | 108 | 145.9 GB |
| PXD029380 | cerebral microvessels | label-free | Q Exactive HF-X | 37 | 36.8 GB |
| PXD014557 | dentate gyrus molecular layer | TMT | Q Exactive | 40 | 26.1 GB |
| PXD007160 | frontal cortex | TMT | Orbitrap Fusion | 211 | 159.3 GB |
| PXD053814 | angular gyrus | not stated | Q Exactive HF | 223 | 144.3 GB |
| PXD012114 | hippocampus | TMT10plex, MS3 | Orbitrap Fusion Lumos | 48 | 29.7 GB |
| PXD037133 | frontal cortex | label-free | LTQ Orbitrap Elite | 16 | 17.1 GB |
| PXD059089 | AD fibroblast-derived neurons | TMT | Orbitrap Fusion Lumos | 12 | 4.2 GB |
| PXD010603 | middle frontal gyrus | not stated | Orbitrap Fusion Lumos | 312 | 631.7 GB |

## PXD015690: proteome and phosphoproteome (Seyfried lab, Emory)

- 27 samples: 10 control, 8 asymptomatic AD, 9 AD.
- Digestion: Lys-C then trypsin; reduced with DTT, alkylated with iodoacetamide.
- Proteome: 24 high-pH fractions. Phosphoproteome: fractions combined into 12
  and enriched by Fe-IMAC (CPTAC protocol).
- MS2: HCD (NCE 38) in the Orbitrap at 50,000 resolution.
- Original search: TMT +229.162932 fixed on K and peptide N-termini, so the
  reagent is TMT 6/10/11-plex, not TMTpro. Plex count is not stated.
- Note: the record says "All resulting raw files (n = 211)", but PRIDE holds
  108 RAW files. 211 is the RAW count of PXD007160, so the text appears to be
  copied from that project. The PRIDE file list (108) is what we use.
- Which RAW files are proteome and which are IMAC-enriched is not yet mapped;
  it is needed because IMAC can co-enrich ADP-ribosylated peptides.

## PXD012114: hippocampus, TMT10plex LC-MS3 (Robinson lab)

- 20 samples in 2 batches of 10 (each batch with a pooled reference),
  TMT10plex, 12 high-pH fractions per batch, each injected twice:
  2 x 12 x 2 = 48 RAW files, matching PRIDE.
- Digestion: trypsin/Lys-C. Alkylation: carbamidomethyl C (fixed in their search).
- Original search: fragment tolerance 0.6 Da, i.e. MS2 in the ion trap with
  MS3 reporter quantification. To be confirmed by step 1.
- Related PRIDE projects: PXD014371, PXD014372.

## PXD029380: cerebral microvessels, label-free (Kuster lab, TUM)

- 37 samples: 12 CAA type 1, 13 AD, 12 controls (one RAW file each).
- SP3 digestion; micro-flow LC (60 min); MS2: HCD (NCE 28) in the Orbitrap at
  15,000 resolution.
- Original search: MaxQuant 1.6.17, carbamidomethyl C fixed; the alkylating
  agent is not named in the sample protocol.

## Not yet read

PXD014557, PXD007160, PXD053814, PXD037133, PXD059089 and PXD010603 have SDRF
files; their labelling and plex will be read from the SDRF (downloaded in
step 1) and confirmed by the acquisition table.
