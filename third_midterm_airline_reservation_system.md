# THIRD MIDTERM
## Airline Reservation System: Events, Live View and Star Schema
**Course:** Big Data and Data Engineering

---

### 1. Purpose
In the second midterm your system analyzed history in batches. In this midterm it also reacts to events as they happen: the backend publishes events to Amazon Kinesis, a live view reads them in seconds, and the same events are stored in S3 and modeled as a star schema that is queried with Athena.

As before, every requirement is verifiable: an automated test suite (the harness) checks your running system and either the requirement is met or it is not. The cheapest architecture that meets the requirements is the best one (R11, R12).

---

### 2. Business scenario (continuation)
The airline wants to know, minute by minute, how many people are searching and booking, and also to analyze the history of searches, bookings and cancellations by date, route and fare class. These two needs have different latency and different data structures, and the midterm is about making that difference explicit:

* **Fast path (seconds):** A consumer reads the Kinesis stream and keeps counters for the last few minutes. It answers `GET /analytics/live`.
* **Analytical path (minutes):** The same events are delivered to S3, cleaned (duplicates, late and out-of-order events) and loaded in micro-batches into a star schema that Athena queries. A star schema is built for analysis, not for per-event updates: it is refreshed every few minutes, not on every event.

Three event types are captured: searches (very frequent; losing one is acceptable, slowing the user down is not), reservations created and reservations cancelled (rare; these are business transactions). You will have to explain why that distinction matters.

Everything not fixed by this document (how events are published, how they reach S3, the tool that builds the star, the attributes you add to the dimensions) is your decision. You must keep the solution as simple and as cheap as the requirements allow and justify each choice (section 5).

---

### 3. Use of artificial intelligence assistants
AI assistants are allowed under the same rule as the previous midterms: you must be able to explain and defend every decision, and the prompt log appendix is mandatory. The harness runs against your deployed system and the oral defense (section 8) asks you to explain and modify what you built.

---

### 4. Requirements and how each one is verified
The harness is a test suite you receive and may run against your own system as often as you like (it injects test events into your stream). The instructor runs the same suite at the oral defense, with the same thresholds but different, undisclosed event data. Your team receives a seed that determines the reference data and your expected answers.

#### 4.1 Reference data and the dirty replay
Generate the reference files for your dimensions with your seed:

```bash
python -m airline_data.generate_p3 --seed <YOUR_SEED> --out ref/
```

* `routes_ref.csv` lists your routes (origin, destination, region).
* `holidays_ref.csv` lists the Colombian public holidays from 2023 to 2027.
* `route_category_history.csv` gives the category of each route over time; some routes change category on `2025-02-01`, so the route dimension has more than one version for them.

During the checks the harness replays about 20,000 events into your stream. The replay contains duplicates (3 %), late events (2 %) and out-of-order events (1 %), and its events carry dates from `2025-01-01` to `2025-03-31`. Their `event_id` starts with `rp-`; your pipeline must process everything, but the star-schema checks only look at those events.

#### 4.2 Requirement table

| ID | Requirement (acceptance criterion) | How the harness verifies it | Pts |
| :--- | :--- | :--- | :---: |
| **R1** | Each search, reservation and cancellation publishes exactly one valid event: contract schema, `event_ts` is when it happened, partition key as specified, no personal data. | Makes 30 searches, 3 reservations and 1 cancellation through the API (searches carry `X-Session-Id`), reads the stream and matches events one to one. | 7 |
| **R2** | No event is lost under a burst and publishing does not slow the API. | 200 searches, 50 at a time: p95 latency at most 1.0 s and exactly 200 events in the stream. | 6 |
| **R3** | `GET /analytics/live` reflects new events within 10 s and counts by event time. | Adds 10 searches, 3 reservations, 1 cancellation and expects those increases; then replays old events and expects them not to appear. | 7 |
| **R4** | Every event reaches the S3 landing zone in at most 5 minutes. | Replays the events into your stream and looks for every distinct `event_id` in S3. | 4 |
| **R5** | The star-schema tables exist in the Glue Data Catalog with the required columns and types, in Parquet; `fact_search` is partitioned by month and partitions are registered. `dim_date` is enriched (weekday name, quarter, public holidays, long weekends) for every day from 2023 to 2027. | Reads table definitions from Glue and compares every `dim_date` row with the expected calendar. | 7 |
| **R6** | Integrity: unique dimension keys, no fact row pointing to a missing dimension row, one fact row per `event_id`. | Counting queries in Athena. | 5 |
| **R7** | The business questions Q1, Q2, Q3, Q4, Q6, Q7 and Q8 of section 4.3 return the right numbers. (Q5 is checked in R9.) | Runs its own SQL on your tables and compares with the expected values (tolerance 0.1 %). | 11 |
| **R8** | Duplicates are removed, late events use their event date, and `POST /admin/refresh-star` finishes within 15 minutes. | Calls the refresh endpoint, then compares counts per event and per date with the expected values. | 6 |
| **R9** | `dim_route` is a type 2 slowly changing dimension and facts use the version valid on the event date. | Checks the versions, validity dates and flags, and the revenue by route category per month. | 8 |
| **R10** | Queries that filter by month do not scan everything, and the Athena workgroup has a per-query data limit of at most 1 GB. | Compares bytes scanned for one month against all months (at most 60 %) and reads the workgroup configuration. | 4 |
| **R11** | Minimal stream: provisioned mode, one shard, default retention (at most 24 h), no enhanced fan-out consumers. | Reads the stream configuration from the Kinesis API. | 3 |
| **R12** | Your monthly cost projection (`cost_projection.yaml`) is at most 1.5 times the instructor's reference solution and never above US$50, and lists Kinesis, S3 and Athena. | Sums your line items and compares them with the limit. | 2 |

The requirements add up to 70 points, which is 70 % of the grade (section 7). The harness takes several minutes to run: it replays the events, waits for them to reach S3 and triggers the star refresh.

> **Budget Note:** The Learner Lab budget is US$50 per student account, shared with everything else you run. A provisioned Kinesis shard is billed for every hour it exists, so create the stream with a script and delete it when you stop working. The star schema is built only from events (you do not need to reload the history of the second midterm).

#### 4.3 Business questions
The management of the airline wants answers to the questions below. They are the starting point of your design: from them you decide the measures, the dimensions and the attributes each dimension needs. The table and column names are fixed by the contract (Appendix A.3) so that the harness can query your model; what you design is everything the questions require.

| ID | Business question | What it needs from the model |
| :--- | :--- | :--- |
| **Q1** | What is the net revenue (reservations minus cancellations) per month and fare class? | Revenue measure; month in the date dimension; fare class dimension. |
| **Q2** | How many reservations and cancellations does each route have (what is its cancellation rate)? | Bookings and cancellations as measures; route dimension. |
| **Q3** | On which days of the week do customers reserve? (Monday to Sunday, by name.) | Weekday name in the date dimension. |
| **Q4** | Which are the ten routes with the highest net revenue? | Revenue by route. |
| **Q5** | What is the net revenue per month by route category, using the category the route had on the day of the event? | History of the route category (type 2) and a join by date. |
| **Q6** | How many searches and how many reservations does each route have (conversion)? | Two fact tables that share the route dimension. |
| **Q7** | How do searches and reservations on public holidays compare with the other days? | Holiday flag in the date dimension, used by both facts. |
| **Q8** | How many reservations are made on the days of a long weekend (a holiday on Friday or Monday that forms a three-day weekend)? | Long-weekend flag in the date dimension. |

Q3, Q7 and Q8 cannot be answered with a plain list of dates: you must enrich `dim_date` with the weekday name, the quarter, whether the day is a public holiday (and its name) and whether it belongs to a long weekend. Use `holidays_ref.csv` for the holidays. A day belongs to a long weekend when a public holiday falls on the Friday or the Monday of its weekend: that holiday day itself (if it is a Friday or a Monday) and the Saturday and the Sunday between. Other public holidays do not make a long weekend.

#### 4.4 What the harness cannot verify
* Whether your justifications are correct and linked to a requirement and to the Well-Architected pillars.
* Whether the live view really reads the stream (the harness checks its behavior, not its code).
* Whether the grain, the dimensions and the type of slowly changing dimension you chose are the right ones for the questions, and whether your diagrams match what is deployed.

These are assessed by the instructor's review of the document and by the oral defense.

---

### 5. Decisions you must make and justify
For each decision write a short paragraph that cites a requirement and one or more Well-Architected pillars.

1. **What goes into a stream and what does not.** Why are searches a good fit for Kinesis and reservations a delicate one? What can be lost without harm and what cannot? In production, how would you avoid losing a reservation event between saving it in the database and publishing it (describe it, you do not implement it)?
2. **Two paths.** Why does the live view read the stream and not Athena? Why is the star schema refreshed every few minutes instead of per event? What would break if you tried to update the star per event?
3. **Landing zone.** How do events get from Kinesis to S3 (managed delivery or your own consumer), and why? What does it cost in latency and money?
4. **Star schema design.** Start from the business questions of section 4.3. For each one write the measure, the fact table and the dimensions it uses, and show them in a bus matrix (question and fact against dimension). State the grain of each fact table, which dimensions are shared (conformed) and which attributes you added to the dimensions beyond the contract, and why.
5. **ETL: choose the best process for this workload.** Between the landing zone and the star schema there is a transformation (deduplicate by `event_id`, assign dates by event time, resolve surrogate keys and the route version valid on the event date, write Parquet, register partitions). The harness only checks the result, not how you build it, so you must analyse the alternatives and choose the best ETL for this process: for example Athena `CTAS` / `INSERT INTO` triggered on a schedule, a Lambda with pandas or DuckDB, or a Glue job. Compare them at least on cost per run and per month, start-up time against the 15-minute refresh limit, ability to handle growth in volume, simplicity of operation, and idempotency (re-running the same batch must not duplicate rows). Justify the choice with numbers from your cost projection and explain when you would change it.
6. **Slowly changing dimensions.** Why type 2 for the route category? What would a type 1 dimension have answered incorrectly? How do you choose the dimension version for a late event?
7. **Dirty events.** How do you deduplicate, and what does "late" and "out of order" change in your design?
8. **Cost and lifecycle.** Which resources exist all the time and which only while testing? Service justification table and cost projection (`cost_projection.yaml` plus a short narrative), connected to the cost optimization and sustainability pillars.

---

### 6. Running the harness

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml     # seed, backend URL, stream name, landing zone, Athena database
pytest                                 # several minutes; writes report.json and report.md
```

* Your backend, stream, landing zone and tables must be running before you start. Use your normal AWS credentials; never commit them.
* The Learner Lab can change public IP addresses when it restarts: update the URL in `config.yaml` before each run.
* If the Learner Lab role cannot do something the harness needs, the report marks that part as failed or not verified; mention such cases in your document.
* Include your final `report.md` in the submission. If a requirement fails, explain why and what you would change.

---

### 7. Deliverables and evaluation

| Deliverable | Content |
| :--- | :--- |
| **Partial submission** | Section 5 draft: event design, star schema diagram with grain and bus matrix, architecture diagram, and first cost projection (before building). |
| **Final submission** | Updated document (sections 5 and 6), repository with backend, consumer, loading job and scripts to create and delete the stream, `config.yaml` (without credentials), `cost_projection.yaml`, final `report.md`, and prompt log appendix. |

| Component | Weight | Source |
| :--- | :---: | :--- |
| **Automated requirements R1–R12** | 70 % | Harness (points in section 4.2) |
| **Document: justifications, Well-Architected, cost narrative, traceability to requirements** | 15 % | Instructor review |
| **Oral defense** | 15 % | Instructor |

---

### 8. Oral defense
All team members must be able to explain any part of the system. The instructor may ask you to change something live (for example, add a measure to a fact table or an attribute to a dimension) and to say what part of the pipeline, the tables and the tests would be affected.

The oral defense is eliminatory for each block: if the team cannot coherently support a decision or a component of a block, the points of that block are voided, including points earned in the harness. The blocks are:
* **R1–R4:** Events and live view
* **R5–R10:** Star schema
* **R11–R12:** Cost and architecture

---

### Appendix A. Contracts

#### A.1 Events
All events (JSON): `event_id` (unique), `event_type`, `event_ts` (UTC, `YYYY-MM-DDTHH:MM:SSZ`, when it happened), `schema_version` (1).

| `event_type` | Extra fields | Partition key |
| :--- | :--- | :--- |
| `search_performed` | `session_id`, `origin`, `destination`, `travel_date`, `results_count` | `session_id` |
| `reservation_created` | `reservation_id`, `flight_id`, `route`, `flight_date`, `fare_class`, `price_cents` | `flight_id` |
| `reservation_cancelled` | same as `reservation_created` | `flight_id` |

`GET /flights/search` publishes one search event per call, taking `session_id` from the optional header `X-Session-Id`. Events never carry the passenger name or other personal data. Events must reach the landing zone (`raw_events_uri`) as JSON text (gzip allowed).

#### A.2 API additions

| Endpoint | Behavior |
| :--- | :--- |
| `POST /reservations/{id}/cancel` | `200` with status: `CANCELLED`, frees the seat, publishes the cancellation event; `404` unknown; `409` already cancelled. |
| `GET /analytics/live?window=5` | `200` `{window_minutes, searches, reservations, cancellations, conversion}` counted by `event_ts` over the last `window` minutes; `conversion = reservations / searches` (`0` if no searches). |
| `POST /admin/refresh-star` | `202` (or `200`). Starts the job that rebuilds the star schema from the landing zone. |
| `GET /admin/refresh-status` | `200` `{"state": "RUNNING" | "SUCCEEDED" | "FAILED"}` |

#### A.3 Star schema (extra columns allowed)

| Table | Required columns |
| :--- | :--- |
| **`dim_date`** | `date_key` (`yyyymmdd`), `full_date`, `year`, `month`, `quarter`, `weekday` (1 = Monday to 7 = Sunday), `weekday_name` (English: Monday ... Sunday), `is_weekend`, `is_holiday`, `holiday_name` (empty if not a holiday), `is_long_weekend`; one row per day from `2023-01-01` to `2027-12-31` |
| **`dim_route`** | `route_key`, `route`, `origin`, `destination`, `region`, `route_category`, `valid_from` (inclusive), `valid_to` (exclusive, current = `9999-12-31`), `is_current` |
| **`dim_fare_class`** | `fare_class_key`, `fare_class` |
| **`fact_search`** | `event_id`, `date_key`, `route_key`, `results_count`, `searches` (=1). One row per distinct event. Partitioned by month (string `YYYY-MM`). |
| **`fact_booking_event`** | `event_id`, `date_key`, `route_key`, `fare_class_key`, `reservation_id`, `event_type`, `bookings`, `cancellations`, `revenue_cents`. Created: `bookings` 1, `revenue` +price. Cancelled: `cancellations` 1, `revenue` -price. |

`date_key` comes from `event_ts`. `route_key` must point to the route version valid on that date. Your Athena workgroup must define a per-query data usage limit of at most 1 GB.

#### A.4 `cost_projection.yaml`

```yaml
assumptions: "searches per day, reservations per day, hours the stream exists"
line_items:
  - {service: "Kinesis", detail: "1 provisioned shard, only while testing", monthly_usd: 3.0}
  - {service: "S3", detail: "...", monthly_usd: 1.0}
  - {service: "Athena", detail: "...", monthly_usd: 0.5}
```

Do not write a total: the harness computes it from the line items. Include every service your system uses.