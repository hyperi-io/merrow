# Diagram templates

One template a level and form, each a whole page block: intro, Mermaid and caption. Start from the one that matches, change the nodes and labels, and keep the structure. `Up` and `Down` are plain text here and links on a page. The rules they follow are in [diagrams.md](diagrams.md).

## L1 Context

The pipeline takes events from agents and cloud APIs and returns results to analysts and downstream tools.

```mermaid
flowchart LR
    accTitle: L1 Context -- Pipeline
    accDescr: Agents and cloud APIs send events to the pipeline. The pipeline returns results to analysts and downstream tools.

    subgraph sources["Sources"]
        agents["Agents"]
        apis["Cloud APIs"]
    end

    pipeline[["Pipeline"]]

    subgraph consumers["Consumers"]
        analysts["Analysts"]
        tools["Downstream<br/>tools"]
    end

    sources -->|events| pipeline
    pipeline -->|results| consumers

    classDef default fill:#F8FAFC,stroke:#64748B,stroke-width:1px,color:#0F172A
    classDef core fill:#DCEBF7,stroke:#0072B2,stroke-width:2px,color:#0B2A3F
    classDef ext fill:#EEF0F2,stroke:#6B7280,stroke-width:1px,stroke-dasharray:4 3,color:#1F2937
    classDef group fill:none,stroke:#64748B,stroke-width:1px,stroke-dasharray:2 4
    class agents,apis,analysts,tools ext
    class pipeline core
    class sources,consumers group
```

*Figure 1. L1 Context -- Pipeline. Sources and consumers sit outside the pipeline.* Up: L0 Landscape. Down: L2 Services -- Pipeline.

## L2 Services, straight boundary

Every event reaches the pipeline's tables through one topic and the loader.

```mermaid
flowchart LR
    accTitle: L2 Services -- Pipeline
    accDescr: Inside the pipeline, sources publish events to the ingest topic. The loader reads the topic, writes rows to tables and sends rejected events to the dead letter topic. Consumers get results from the tables.

    sources["Sources"]

    subgraph pipeline["Pipeline"]
        topic[("Ingest<br/>topic")]
        loader[["Loader"]]
        tables[("Tables")]
        dlq[("Dead letter<br/>topic")]
    end

    consumers["Consumers"]

    sources -->|events| topic
    topic --> loader
    loader --> tables
    loader -.-> dlq
    tables -->|results| consumers

    classDef default fill:#F8FAFC,stroke:#64748B,stroke-width:1px,color:#0F172A
    classDef store fill:#DDF3EC,stroke:#00785A,stroke-width:1px,color:#0B3327
    classDef async fill:#F6E6EF,stroke:#A8517F,stroke-width:1px,color:#3D1529
    classDef error fill:#FBE3D6,stroke:#C2410C,stroke-width:1px,color:#4A1A05
    classDef ext fill:#EEF0F2,stroke:#6B7280,stroke-width:1px,stroke-dasharray:4 3,color:#1F2937
    classDef group fill:none,stroke:#64748B,stroke-width:1px,stroke-dasharray:2 4
    class sources,consumers ext
    class topic async
    class tables store
    class dlq error
    class pipeline group
```

*Figure 2. L2 Services -- Pipeline. The loader takes the dead letter path only for rejected events.* Up: L1 Context -- Pipeline. Down: L3 Components -- Loader.

## L3 Components, stacked boundary

The loader checks every event before it routes and writes it, so a rejected event never reaches a table.

```mermaid
flowchart TB
    accTitle: L3 Components -- Loader
    accDescr: The loader reads from the ingest topic. Inside, it consumes, validates, routes and writes events in that order. It writes rows to tables and sends rejected events to the dead letter topic.

    topic[("Ingest topic")]

    subgraph loader["Loader"]
        direction LR
        consume["Consume"] --> validate["Validate"] --> route[["Route"]] --> write["Write"]
    end

    tables[("Tables")]
    dlq[("Dead letter topic")]

    topic -->|events| loader
    loader -->|rows| tables
    loader -.->|rejected| dlq

    classDef default fill:#F8FAFC,stroke:#64748B,stroke-width:1px,color:#0F172A
    classDef store fill:#DDF3EC,stroke:#00785A,stroke-width:1px,color:#0B3327
    classDef async fill:#F6E6EF,stroke:#A8517F,stroke-width:1px,color:#3D1529
    classDef error fill:#FBE3D6,stroke:#C2410C,stroke-width:1px,color:#4A1A05
    classDef group fill:none,stroke:#64748B,stroke-width:1px,stroke-dasharray:2 4
    class topic async
    class tables store
    class dlq error
    class loader group
```

*Figure 3. L3 Components -- Loader. Rejected events leave from the validate step.* Up: L2 Services -- Pipeline. Down: L4 Detail -- Loader routing decision.

## L4 Detail, stacked stages (pattern B)

The loader's eleven steps fall into three stages: collect, process and deliver.

```mermaid
flowchart TB
    accTitle: L4 Detail -- Loader stages
    accDescr: Three stages run in order. Collect receives, decodes, stamps and buffers events. Process validates, enriches, routes and batches them. Deliver writes batches, commits offsets and emits metrics.

    subgraph s1["1 Collect"]
        direction LR
        receive["Receive"] --> decode["Decode"] --> stamp["Stamp header"] --> buffer["Buffer"]
    end
    subgraph s2["2 Process"]
        direction LR
        validate["Validate"] --> enrich["Enrich"] --> route["Route"] --> batch["Batch"]
    end
    subgraph s3["3 Deliver"]
        direction LR
        write["Write"] --> commit["Commit offsets"] --> metrics["Emit metrics"]
    end
    s1 --> s2 --> s3

    classDef default fill:#F8FAFC,stroke:#64748B,stroke-width:1px,color:#0F172A
    classDef group fill:none,stroke:#64748B,stroke-width:1px,stroke-dasharray:2 4
    class s1,s2,s3 group
```

*Figure 4. L4 Detail -- Loader stages. Read each stage left to right, then down.* Up: L3 Components -- Loader.

## L4 Detail, decision flow

An auth event goes to `events.auth`, any other valid event to `events.main`, and an invalid one to the dead letter topic.

```mermaid
flowchart LR
    accTitle: L4 Detail -- Loader routing decision
    accDescr: An event is read and checked. Invalid events go to the dead letter topic. Valid auth events are written to events.auth and all other valid events are written to events.main.

    read(["Event read"])
    valid{"Valid?"}
    kind{"Auth event?"}
    dead(["To dead letter"])
    auth(["To events.auth"])
    main(["To events.main"])

    read --> valid
    valid -->|yes| kind
    valid -.->|no| dead
    kind -->|yes| auth
    kind -->|no| main

    classDef default fill:#F8FAFC,stroke:#64748B,stroke-width:1px,color:#0F172A
    classDef store fill:#DDF3EC,stroke:#00785A,stroke-width:1px,color:#0B3327
    classDef decision fill:#FCF1D6,stroke:#9A6700,stroke-width:1px,color:#3D2A00
    classDef error fill:#FBE3D6,stroke:#C2410C,stroke-width:1px,color:#4A1A05
    class valid,kind decision
    class dead error
    class auth,main store
```

*Figure 5. L4 Detail -- Loader routing decision.* Up: L3 Components -- Loader.

## L4 Detail, side by side (pattern C)

Every table carries the same common header, and only the non-landing tables add data columns.

```mermaid
flowchart LR
    accTitle: L4 Detail -- Common header against a complete table schema
    accDescr: The landing table events.main holds the common header alone. Every other table, such as events.auth, holds the same common header plus its data columns.

    subgraph landing["Landing table events.main"]
        h1["Common header<br/>_timestamp ..."]
    end

    subgraph other["Non-default table events.auth"]
        direction LR
        h2["Common header<br/>_timestamp ..."]
        d2["Data columns<br/>user_id ..."]
        h2 ~~~ d2
    end

    landing ~~~ other

    classDef default fill:#F8FAFC,stroke:#64748B,stroke-width:1px,color:#0F172A
    classDef core fill:#DCEBF7,stroke:#0072B2,stroke-width:2px,color:#0B2A3F
    classDef store fill:#DDF3EC,stroke:#00785A,stroke-width:1px,color:#0B3327
    classDef group fill:none,stroke:#64748B,stroke-width:1px,stroke-dasharray:2 4
    class h1,h2 core
    class d2 store
    class landing,other group
```

*Figure 6. L4 Detail -- Common header against a complete table schema. The common header is identical in every table, and non-default tables add data columns.* Up: L3 Components -- Loader.

## L4 Detail, sequence

The loader commits the topic offset only after the batch is in the tables, retrying once on a timeout.

```mermaid
sequenceDiagram
    accTitle: L4 Detail -- Batch write with retry
    accDescr: The loader polls a batch from the ingest topic, inserts it into the tables, retries once on timeout, then commits the offset.
    autonumber
    box Transport
        participant topic as Ingest topic
    end
    box Loader
        participant loader as Loader
    end
    box Storage
        participant tables as Tables
    end
    topic->>loader: Poll batch
    loader->>tables: Insert batch
    alt timeout
        loader->>tables: Retry insert
    end
    tables-->>loader: Ack
    loader->>topic: Commit offset
```

*Figure 7. L4 Detail -- Batch write with retry.* Up: L3 Components -- Loader.

6 participants or fewer, with the labels they have on the L2 and L3 diagrams.

## L4 Detail, state

A batch seals at its size or age limit and ends written, or failed once its retries run out.

```mermaid
stateDiagram-v2
    direction LR
    accTitle: L4 Detail -- Batch lifecycle
    accDescr: A batch is open, then sealed when it reaches a size or age limit, then either written or, after retries are exhausted, failed.
    [*] --> Open
    Open --> Sealed: limit reached
    Sealed --> Written: insert ok
    Sealed --> Failed: retries exhausted
    Written --> [*]
    Failed --> [*]
    classDef store fill:#DDF3EC,stroke:#00785A,stroke-width:1px,color:#0B3327
    classDef error fill:#FBE3D6,stroke:#C2410C,stroke-width:1px,color:#4A1A05
    class Written store
    class Failed error
```

*Figure 8. L4 Detail -- Batch lifecycle.* Up: L3 Components -- Loader.
