# User Stories
## Cloud Compute / Conformance Data Model Use Cases

## Introduction

This document organizes the provided use cases into persona-centered user stories. The stories describe what each role needs to view, trace, export, compare, or validate across cloud compute runs, model versions, conformance workflows, hazard outputs, and consequences analyses. They are intended to support data model design, workflow prioritization, and implementation planning by making each need explicit in terms of the user, the desired capability, and the business or technical reason for it.

---

## Personas

| Persona | Description | Stories |
|---------|-------------|--------:|
| CC Admin | Manages cloud compute infrastructure, monitors execution reliability, tracks costs, and oversees hot-fix remediation for conformance runs. | 4 |
| Conformance Lead | Responsible for assessing whether basin models meet conformance requirements and driving remediation when checks fail. | 2 |
| Conformance Lead / Leadership / FEMA | Cross-role need for full traceability of published hazard and flow results to satisfy regulatory and audit requirements. | 1 |
| Consequences Analyst | Evaluates flood-induced damages, calculates risk metrics (AAL), and quantifies uncertainty across AEP frequencies and structure inventories. | 4 |
| Data Prep Lead | Oversees the preparation, naming, and provenance of authoritative input datasets used by hydrologic and hydraulic models. | 3 |
| H&H Engineer | Builds, runs, and validates hydrologic and hydraulic models (HEC-HMS, HEC-RAS, ResSim); primary user of model outputs and parameters. | 11 |
| H&H Engineer / Conformance Lead | Cross-role need for reviewing numerical errors and failed events that affect both model quality and conformance decisions. | 1 |
| H&H Engineer / Integration Lead | Cross-role need for understanding upstream/downstream model relationships to validate sequencing and configuration. | 1 |
| Hazard Analyst | Analyzes frequency-based flood hazard outputs and traces results back to contributing events. | 1 |
| Integration Lead | Manages linkage configurations between model components and reviews version-to-version differences across calibration and conformance variants. | 2 |
| Leadership / FEMA | Executive and regulatory stakeholders who need high-level risk summaries and confidence bounds to support decisions and communications. | 2 |
| Non-PTS Data Scientist | External analyst who consumes cloud-compute outputs for independent research or validation outside the PTS platform. | 1 |
| **Total** | | **33** |

---

## CC Admin

| # | Title | I need to... | So that I can... |
|---|-------|-------------|-----------------|
| 1 | All Versions | Determine which manifest, linkage version, and plugin versions were used for an event | Audit exactly what executed *(execution provenance · auditing & troubleshooting · reproducibility)* |
| 2 | Reliability and Performance | Understand how long a model or event took to run, identify failed events, and review error messages | Monitor reliability and performance *(platform health · identify recurring failures · operational reliability)* |
| 3 | Re-runs and Hotfixes | Identify which events required hot-fix reruns, understand the underlying issue, and determine which model version resolves it | Manage the hot-fix queue *(track remediation · reduce repeated failures · improve release management)* |
| 4 | Resources and Cost Estimates | Evaluate run costs, basin costs, month-to-date spending, projected completion costs, and resource utilization | Control and forecast spend *(budget management · resource planning · cost forecasting)* |

---

## Conformance Lead

| # | Title | I need to... | So that I can... |
|---|-------|-------------|-----------------|
| 5 | Conformance Metrics | Determine whether a basin meets conformance metrics and identify failing checks | Make pass/fail decisions and identify areas requiring remediation *(conformance gate reviews · required attribute validation · model quality improvement)* |
| 6 | Event Filtering | Perform statistical analysis on model outputs and workflow stages to support event filtering | Reduce unnecessary RAS runs *(reduce computational burden · improve workflow efficiency · support future event-filtering strategies)* |

---

## Conformance Lead / Leadership / FEMA

| # | Title | I need to... | So that I can... |
|---|-------|-------------|-----------------|
| 7 | Result Provenance | Trace a hazard, flow, precipitation, or depth result back to the event that produced it | Defend the numbers and provide traceability *(regulatory review · defensible science · auditability of published results)* |

---

## Consequences Analyst

| # | Title | I need to... | So that I can... |
|---|-------|-------------|-----------------|
| 8 | At-Risk Structures | Evaluate losses at selected AEP frequencies for individual structures and entire basins | Identify higher-risk structures and compare damages *(risk prioritization · structure-to-structure comparison · basin-wide risk assessment)* |
| 9 | Damage and Risk Reporting | Calculate Average Annualized Loss (AAL) for structures and basins | Report damages and risk *(risk communication · reporting and planning support)* |
| 10 | Hazard Grids and Frequencies | Identify which hazard grid versions were used in consequence analyses | Assemble and verify consequence model inputs *(input traceability · analysis reproducibility)* |
| 11 | Uncertainty | Calculate mean damages and standard deviations across realizations for each AEP | Quantify uncertainty *(confidence assessment · decision support)* |

---

## Data Prep Lead

| # | Title | I need to... | So that I can... |
|---|-------|-------------|-----------------|
| 12 | Authoritative Dataset Completion | Determine whether all required preparation and scoping datasets are complete and correctly named | Close out data preparation *(data readiness verification · SOP compliance · dataset tracking)* |
| 13 | Dam Scoping Table | Visualize the Dam Scoping Table spatially | Connect scoping decisions with geographic datasets *(spatial validation · improved planning and review)* |
| 14 | Data Source Traceability | Identify the source, version, and acquisition date of datasets such as terrain and NLCD | Document provenance of inputs *(metadata management · data governance · reproducibility)* |

---

## H&H Engineer

| # | Title | I need to... | So that I can... |
|---|-------|-------------|-----------------|
| 15 | Comparison of Observed vs Computed Data | Compare modeled frequency results against observed gage data | Verify model calibration and frequency behavior |
| 16 | Export Models | Export or download models | Perform additional analysis within HEC-HMS and HEC-RAS |
| 17 | Flood Validation | View modeled flood extents for events of interest | Validate calibration events and explore results |
| 18 | Dam and Levee Breach Locations | Identify where dams and levees fail during events | Assess structure failure behavior in the models |
| 19 | Input Datasets | Identify supporting datasets and versions used by a model | Reproduce and contextualize a run |
| 20 | Model Features | Verify feature connectivity and linkages across RAS, HMS, and ResSim models | Validate model setup |
| 21 | Model Versions | Identify which model version produced a result | Trust and trace the information being reviewed |
| 22 | RAS Parameters Outside RAS | View key model parameters (Manning's n, timestep, simulation window) outside of RAS | Perform quality control reviews |
| 23 | Starting Conditions | Review initial conditions such as reservoir elevations for a run | Understand the simulation setup |
| 24 | Validate HMS and RAS Flows | Compare peak flows between HMS and RAS at the same location | Assess model-to-model consistency |
| 25 | Verify Naming Conventions | Verify feature names against authoritative naming standards | Maintain naming consistency |

---

## H&H Engineer / Conformance Lead

| # | Title | I need to... | So that I can... |
|---|-------|-------------|-----------------|
| 26 | Errors and Events | Review volume errors, failed events, and failure causes | Identify and resolve numerical issues |

---

## H&H Engineer / Integration Lead

| # | Title | I need to... | So that I can... |
|---|-------|-------------|-----------------|
| 27 | Model Connections | Identify upstream and downstream model relationships | Validate sequencing and model configuration |

---

## Hazard Analyst

| # | Title | I need to... | So that I can... |
|---|-------|-------------|-----------------|
| 28 | Trace Results | Determine which events contributed to a 100-year or 2,000-year hazard result | Trace hazard outputs to their producing events |

---

## Integration Lead

| # | Title | I need to... | So that I can... |
|---|-------|-------------|-----------------|
| 29 | Diffs Between Model Versions | Identify differences between calibration and conformance model variants | Manage multiple linkage variants |
| 30 | Linkage Diffs | Review changes between linkage versions | Evaluate and approve linkage updates |

---

## Leadership / FEMA

| # | Title | I need to... | So that I can... |
|---|-------|-------------|-----------------|
| 31 | Uncertainty | Understand uncertainty ranges associated with estimates | Communicate confidence bounds appropriately |
| 32 | Understand Risk | Understand flood hazard at standard frequencies for a basin | Evaluate the overall risk picture |

---

## Non-PTS Data Scientist

| # | Title | I need to... | So that I can... |
|---|-------|-------------|-----------------|
| 33 | Export Results | Export run results | Perform independent analyses using cloud-compute outputs |

---