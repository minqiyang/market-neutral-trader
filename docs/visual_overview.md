# Visual Overview

This page collects the public diagrams for the post-PR #109 repository state.
The diagrams describe research, replay, paper, demo dry-run, guarded Demo
boundaries, and disabled-live boundaries only.

## System Workflow

```mermaid
flowchart LR
  A["Market data / fixtures"] --> B["Normalized order book"]
  B --> C["Complement scanner"]
  C --> D["Fee / slippage / failed-leg simulator"]
  D --> E["Paper proposal"]
  E --> F["Paper ledger"]
  F --> G["Risk decision"]
  G --> H["Manual approval"]
  H --> I["Kalshi Demo dry-run / guarded Demo submit boundary"]
  I --> J["Demo reconciliation"]
  J --> K["Rolling validation"]
  K --> L["Disabled private-live gate"]
```

## Six-Layer Architecture

```mermaid
flowchart TB
  L1["Layer 1: recorder"] --> L2["Layer 2: replay / simulator"]
  L2 --> L3["Layer 3: paper ledger / reconciliation"]
  L3 --> L4["Layer 4: risk / manual approval / monitoring"]
  L4 --> L5["Layer 5: Kalshi Demo dry-run / guarded boundary / reconciliation"]
  L5 --> L6["Layer 6: disabled private-live gate"]
```

## Safety Gate Flow

```mermaid
flowchart LR
  A["Candidate"] --> B["Fee / slippage checks"]
  B --> C["Stale / data-gap checks"]
  C --> D["Exposure / loss checks"]
  D --> E["Reconciliation health"]
  E --> F["Kill switch"]
  F --> G["Manual approval"]
  G --> H["Demo dry-run / guarded Demo boundary"]
  H --> I["Demo reconciliation health"]
  I --> J["Private live remains disabled"]
```

## Public / Private Boundary

```mermaid
flowchart TB
  subgraph Public["Public repo"]
    P1["Research"]
    P2["Replay"]
    P3["Paper workflow"]
    P4["Demo dry-run / guarded Demo boundary"]
    P5["Disabled live gate"]
  end

  subgraph Private["Private evidence"]
    E1["30-90 days read-only data"]
    E2["30+ days paper history"]
    E3["Validated fees / slippage"]
    E4["Zero unresolved mismatches"]
    E5["Compliance review"]
  end

  subgraph Excluded["Not in public repo"]
    X1["Production credentials"]
    X2["Production endpoints"]
    X3["Wallets or brokers"]
    X4["Real-money execution"]
    X5["Auto-trading loop"]
  end
```

The public repository does not contain production endpoints, credentials,
wallets, broker integration, live order placement, strategy optimization,
investment advice, executable trading advice, production-readiness claims, or
profitability claims.
