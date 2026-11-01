# Iranian Crypto Exchanges Compliance & Accuracy Matrix

This document tracks the operational and compliance status of Iranian cryptocurrency exchanges within AlertG.

> **Notice:** Status classifications are internal operational and risk-management decisions established by the system owner. This document contains technical operational facts and does not constitute formal legal counsel.

| Exchange ID | Display Name | Operational Status | Accuracy Gate Status | Date Checked | Source / Basis of Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `tabdeal` | Tabdeal (تبدیل) | **APPROVED** (Wave 1) | **PASSED** (Median Diff: 0.0000%, Max Diff: 0.3891%) | 2026-11-01 | Public API probe verified (`/r/api/v1/exchangeInfo`, `/r/plots/market_information/`), 1037 active spot pairs, Accuracy Gate passed. Not designated in June 2026 OFAC actions. |
| `nobitex` | Nobitex (نوبیتکس) | **FROZEN** | N/A (Frozen) | 2026-11-01 | Designated in 2 June 2026 OFAC listings. Code frozen: no new features, no active polling in crypto v2. Legacy fallback only. |
| `wallex` | Wallex (والکس) | **FROZEN** | N/A (Frozen) | 2026-11-01 | Designated in 2 June 2026 OFAC listings. Code frozen: no new features, no active polling in crypto v2. Legacy fallback only. |
| `ramzinex` | Ramzinex (رمزینکس) | **FROZEN** | N/A (Frozen) | 2026-11-01 | Designated in 2 June 2026 OFAC listings. Code frozen: no new features, no active polling in crypto v2. Legacy fallback only. |
| `bitpin` | Bitpin (بیت‌پین) | **FROZEN** | N/A (Frozen) | 2026-11-01 | Designated in 2 June 2026 OFAC listings. Code frozen: no new features, no active polling in crypto v2. Legacy fallback only. |
| `bitbarg` | Bitbarg (بیت‌برگ) | **FROZEN** | Pending Check | 2026-11-01 | Deferred to subsequent wave. Requires dedicated compliance review and Accuracy Gate before inclusion. |
| `tetherland` | Tetherland (تترلند) | **FROZEN** | Pending Check | 2026-11-01 | Deferred to subsequent wave. Requires dedicated compliance review and Accuracy Gate before inclusion. |
| `abantether` | AbanTether (آبان‌تتر) | **FROZEN** | Pending Check | 2026-11-01 | Deferred to subsequent wave. Requires dedicated compliance review and Accuracy Gate before inclusion. |
| `exir` | Exir (اکسیر) | **FROZEN** | Pending Check | 2026-11-01 | Deferred to subsequent wave. Requires dedicated compliance review and Accuracy Gate before inclusion. |
| `sarmayex` | Sarmayex (سرمایکس) | **FROZEN** | Pending Check | 2026-11-01 | Deferred to subsequent wave. Requires dedicated compliance review and Accuracy Gate before inclusion. |

---

### Status Definitions:
- **APPROVED:** Active in Crypto Engine v2, selectable in alert creation, covered by automated catalog discovery, dedicated rate-limited poller.
- **FROZEN:** Endpoints are not called by any new code or probes. Existing legacy paths remain dormant or isolated behind legacy routes.
- **BLOCKED:** Explicitly rejected by API gateway and validation layers with `PROVIDER_BLOCKED` or `UNKNOWN_EXCHANGE`.
