# Privacy & Security Note — Ek Baithak (DPDP Act, 2023)

All data in this prototype is synthetic, but it is handled as if it were real customer data.

## 1. Collect only what each step needs
| Step | Collected | Purpose | Not collected |
|---|---|---|---|
| Advisor | Business type, staff, sites, city, needs, optional current spend | Recommend an eligible bundle | No name, phone or ID to get a price |
| GSTIN lookup | GSTIN (optional) | Pre-fill business, check eligibility | No turnover or returns data |
| KYC | GST cert, Udyam cert, signatory ID, address proof (≤ 90 days) | Legal KYC for business connections; install address | No Aadhaar number stored; no extra documents |
| Order | Business name, products, install slot, consent ID | Fulfilment and billing | No card data (PCI-compliant gateway) |

## 2. Consent first (Section 6)
- The consent screen appears in the owner's language **before** any upload, each purpose listed separately (`/api/consent/purposes`).
- KYC and installation are required; WhatsApp updates and marketing are optional and **off by default**.
- Each consent is stored in a purpose-tagged ledger: consent ID, purposes, language, time, retention text.
- KYC endpoints refuse to run without an active consent (HTTP 403). One-tap withdrawal stops optional processing and triggers image deletion.

## 3. Minimise exposure
- GSTIN / Udyam / ID numbers are masked in the UI, API responses and logs (`37••••••••••1ZS`).
- Uploaded images are processed **in memory** and never written to disk in this prototype.
- Append-only audit log of every lookup, consent and verdict, with masked identifiers only.
- Saathis see leads, scores and reasons — never documents. The propensity model uses business attributes only.

## 4. Retention
| Data | Retention |
|---|---|
| KYC document images | 30 days after activation; immediately on rejection, abandonment > 30 days or withdrawal |
| Extracted KYC fields + verdict | Contract term + period required by DoT telecom KYC and tax rules |
| Advisor sessions with no order | 90 days, then anonymised (segment / city only) |
| Audit log | 1 year, masked identifiers only |

## 5. Security controls
- TLS 1.2+ in transit, AES-256 at rest, secrets in a vault (production).
- Registry, DigiLocker and e-Sign calls only via signed server-to-server APIs.
- KYC integrity: mod-36 check digit, registry status (cancelled / suspended blocked), cross-document checks, blur and skew detection. Uncertain cases go to a human (NEEDS_REVIEW), never auto-approved.
- GenAI never sees documents or identifiers and cannot choose products.
- Upload type and size checks (images ≤ 8 MB); rate limits on lookup APIs to stop GSTIN enumeration (production).

## 6. Rights & grievance
Access, correction and erasure from the tracker or helpline 121; a named Grievance Officer responds
within the statutory timeline; breaches are notified to the Data Protection Board and affected owners.
