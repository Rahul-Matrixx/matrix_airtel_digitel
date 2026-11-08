# Architecture — Ek Baithak

```mermaid
flowchart LR
  subgraph Channels
    O[Business owner<br/>phone browser · Hindi / English · voice]
    L[WhatsApp / QR / Bazaar Cluster link<br/>?saathi= code carries attribution]
    S[Saathi: field rep or channel partner]
  end
  subgraph App[Mobile PWA]
    A1[1 Advisor chat<br/>chips · free text · 🎤]
    A2[2 Quote & checkout<br/>Rozana · Bill-Swap · Switch Shield · Grow Ladder]
    A3[3 Consent + Smart KYC]
    A4[4 Tracker<br/>promise date · late-day credit]
    BO[Saathi back office<br/>win-back queue · commissions]
  end
  subgraph API[FastAPI services]
    R[Rules engine — deterministic<br/>tier · size · GSTIN · requires_one_of]
    P[Pricing<br/>One-Bill · cluster · GST · setup waiver]
    K[KYC service<br/>multi-pass OCR → check digit → registry → cross-checks]
    OR[Order orchestration<br/>parallel survey · milestones · SLA credit]
    M[Propensity<br/>LightGBM + SHAP]
    LLM[(Optional LLM<br/>rephrase only)]
  end
  subgraph Data
    C[(product_catalogue)]
    G[(GSTIN + Udyam registries<br/>prod: GSTN / Udyam / DigiLocker / e-Sign)]
    LD[(smb_leads)]
    PV[(Privacy layer<br/>consent ledger · audit log · masked IDs)]
  end
  O --> A1
  L --> A1
  S --> BO
  A1 --> R --> C
  R -.explanation text only.-> LLM
  A2 --> P
  A3 --> K --> G
  A3 --> PV
  A4 --> OR --> PV
  BO --> M --> LD
  BO -->|advisor link with Saathi code| O
```

## Data flow
owner or link → advisor profile → rules engine + catalogue → quote → consent ledger → KYC
(OCR → GSTIN check digit & repair → registry lookup → name / date / PIN / signatory checks → verdict)
→ order (survey booked at checkout) → tracker. Unclosed sessions and dropped leads → propensity model
→ Saathi queue → advisor link back to the owner, with the Saathi's code for commission.

## Design rule
The catalogue rules decide **what** is sold; language models only decide **how** it is explained.
Recommendations are therefore auditable, compliant, and identical for the same input in every live test.

## Production swaps
| Demo | Production |
|---|---|
| CSV registries | GSTN, Udyam, DigiLocker pull, e-Sign via signed server-to-server APIs |
| JSON store in `.state/` | Encrypted database (AES-256 at rest), secrets in a vault |
| Browser speech recognition | Missed-call → WhatsApp voice notes in 10+ languages |
| Demo clock | Real install slots per city |
