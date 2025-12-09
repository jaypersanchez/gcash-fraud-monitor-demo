
# Fraud Pattern Reference Guide for E-Wallet Transfers (GCash-Style)

This document summarizes the main fraud patterns, behaviors, and classifications used in digital wallet ecosystems such as GCash. It serves as reference material for designing detection rules, ML models, and graph-analysis-based alerts.

---

## 1. Behavioral Anomalies

Fraudsters behave differently from normal users. These patterns often indicate account compromise or mule activity.

### Characteristics
- Sudden high transfer activity (e.g., 20+ transfers in 1 hour)
- Cash-in → cash-out within minutes
- Unusual login times or impossible travel
- Multiple device changes in short time periods
- High login/OTP velocity
- Significant departure from user’s historical behavior

---

## 2. Network-Based Patterns (Graph/Neo4j Patterns)

Fraud often emerges from relationships between accounts, devices, and transactions.

### A. Shared Device → Many Accounts
A single phone/device is used by multiple accounts.

### B. Shared Recipient
Many senders funnel money to one wallet.

### C. Chain Transfers (Layering)
Money hops through multiple accounts in a short time (A → B → C → D).

### D. Star Pattern (Mule Hub)
One account receiving from multiple unrelated sources.

### E. Circular Transfers
Funds circulate between accounts (A → B → C → A).

### F. Triangulation
Chains of accounts/devices interacting to obscure the true source.

---

## 3. Device & Identity Signals

Device anomalies strongly correlate to fraud operations.

### Indicators
- Same device linked to multiple high-risk accounts
- Brand new device → instant cash-out
- Rooted/jailbroken device
- Emulator presence
- Device fingerprint inconsistent with historical profile
- Sudden changes in device/browser fingerprint

---

## 4. Transaction Characteristics

These are direct anomalies observed in transaction details.

### Examples
- Transactions repeatedly just below AML thresholds
- Unusual or repeated high-value transfers
- Multiple identical transfers to same target
- Spike in failed transfer attempts
- Risky cash-in methods (compromised cards, crypto bridges)
- Rapid-fire micro-deposits (testing stolen accounts)

---

## 5. Money Flow Patterns (Temporal + Graph)

Combines timing + relationship behavior.

### Patterns
- **Fan-out**: One account sending to many accounts rapidly
- **Fan-in**: Many accounts sending to a single destination
- **Flash transfers**: Money quickly enters then exits
- **Dormant → active → cash-out** pattern
- **Automated/scripted transactions** (multiple transfers at same minute)

---

# Fraud Categories

Below are the industry-standard classifications for mobile-wallet fraud.

---

## 1. Account Takeover (ATO)

Occurs when the real owner loses control of their account.

### Signs
- New device linked then immediate transfers
- Password reset + OTP surge
- Sudden cash-out or bank withdrawal
- Login from unusual location/IP

---

## 2. Scam / Social Engineering

The user is tricked into sending money.

### Signs
- Normal device & IP (because it's the victim)
- Unusual transaction size or new recipient
- Repeated transfers to unknown contacts

---

## 3. Mule Account

Used as a middle point for stolen or illicit money.

### Signs
- Receives funds from many unrelated sources
- Sends out funds quickly
- Connected to suspicious devices
- Part of chain hopping or star patterns

---

## 4. Merchant Fraud

For e-commerce integrations.

### Examples
- Fake merchant accounts receiving multiple payments
- Rapid refund requests
- Dispute-heavy behavior

---

## 5. Synthetic Identity Fraud

Fraudster creates multiple fake identities.

### Signs
- Multiple accounts share same device
- Disposable devices, SIMs, or emails
- Inconsistent identity documents (if KYC exists)

---

## 6. Money Laundering

Classic AML behaviors.

### Examples
- Structured transactions (“smurfing”)
- Layering via multiple hops
- Cross-border transfer anomalies
- Round-tripping funds into same origin

---

# Usage in Your Demo

These patterns can be translated into:
- Rule-based alerts
- Graph queries (Neo4j)
- Risk scoring logic
- Visual fraud maps

This document serves as a reference for building detection logic in your demo application.
