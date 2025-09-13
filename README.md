# Donizo Smart Semantic Pricing Engine

This project implements a **semantic material pricing engine** designed to handle chaotic, fuzzy, and multilingual contractor queries for renovation materials. It simulates the core logic of Donizo’s pricing brain, combining embeddings, vector search, VAT rules, margin protection, and adaptive feedback loops to produce accurate renovation quotes globally.

The engine supports:

* Fuzzy voice/text queries across multiple languages (incl. French).
* Material retrieval across vendors, units, and geographic regions.
* Quote generation with VAT & contractor margin logic.
* Feedback-driven confidence scoring that adapts over time.

---

### Architecture & Flow

```
+-----------------+        +------------------+       +--------------------+
| Contractor Query| -----> | Query Interpreter| ----> | Semantic Search    |
| (text/voice)    |        | (normalize,      |       | (pgvector in Postgres)|
|                 |        | tokenize)        |       +--------------------+
+-----------------+                                    |
                                                       v
                                      +-------------------------------+
                                      | Best Match Material(s)        |
                                      | (confidence, VAT, region,     |
                                      | unit normalization, margin)   |
                                      +-------------------------------+
                                                       |
                                                       v
                                      +-------------------------------+
                                      | Quote Generator API           |
                                      | (labor, VAT, margin, fallback)|
                                      +-------------------------------+
                                                       |
                                                       v
                                      +-------------------------------+
                                      | Feedback Endpoint             |
                                      | (verdict, user, adaptation)   |
                                      +-------------------------------+
```

---

### Components

#### 1. Data Ingestion

* Load/simulate catalog of **1,000–5,000+ materials** with fields:

  * `material_name`, `description`, `unit_price`, `unit`, `region`, `vendor`, `vat_rate`, `quality_score`, `updated_at`, `source`.
* Normalize units (`€/m²` vs `€/sqm`) for consistency.
* Store:

  * Metadata (PostgreSQL tables).
  * Embeddings (pgvector).

#### 2. Query Input Handling

* Accept **fuzzy, multilingual queries**.
* Extract signals:

  * Product type, region, quality, unit.
* Handle free-form contractor phrasing (voice/text).

#### 3. Embedding & Vector DB Setup

* **Embedding source**: `material_name + description`.
* **DB**: PostgreSQL + pgvector (preferred).

  * Chosen for **robustness, scalability, ecosystem maturity**, and ability to combine vectors + structured SQL filters.
* **Model**: OpenAI (or BGE/Instructor if open-source) → selected for **semantic accuracy across multilingual inputs**.

#### 4. Semantic Match API

**Endpoint:**

```
GET /material-price?query=cement waterproof glue&region=Île-de-France
```

**Returns:**

* `material_name`, `description`, `unit_price`, `unit`, `region`, `similarity_score`, `confidence_tier`, `updated_at`, `source`.

**Constraints:**

* <500ms response time (1,000+ records).
* Graceful degradation (best guess or clarification).
* Bonus: support filters (`unit`, `region`, `vendor`, `quality_score`) + `limit`.

#### 5. Quote Generator API

**Endpoint:**

```
POST /generate-proposal
```

Input: contractor transcript.
Output: tasks with:

* Region-specific pricing.
* VAT logic (10% bathroom reno, 20% new build).
* Contractor margin (e.g., 25%).
* Estimated labor.
* Confidence score.
* Fallback if missing material.

#### 6. Feedback Endpoint

**Endpoint:**

```
POST /feedback
```

Captures:

* Quote/task reference, user type, verdict, comments.
* Impacts **confidence scoring curve**, adjusts pricing logic, and improves future proposals.
* Links signals to **materials, region, VAT, or margin logic**.

---

### Design Decisions & Tradeoffs

| Aspect              | Decision & Justification                                                             |
| ------------------- | ------------------------------------------------------------------------------------ |
| Vector DB           | **Postgres + pgvector** → unified metadata + vectors, scales well, stable ecosystem. |
| Embedding Model     | **OpenAI** (or BGE/Instructor) → high multilingual semantic accuracy.                |
| API Design          | RESTful endpoints for simplicity; async jobs planned for scaling.                    |
| Latency vs Accuracy | <500ms prioritized, fallback best-guess if confidence low.                           |
| Data Scale          | Start 1k–5k records; design scales to 1M+ with indexing + caching.                   |

---

### System Learning & Adaptation

* Feedback adjusts confidence scoring dynamically.
* Adaptive multipliers per region/vendor/quality.
* Logs for retraining embeddings or rules.
* Trust calibration through contractor vs client verdicts.
* Analytics detect supply issues or overpriced vendors.

---

### Second-Order Thinking

1. **What breaks at 1M+ products / 10k daily queries?**

   * DB indexing and query latency.
   * Fix: DB sharding, caching, async query workers, pre-computed ANN indexes.

2. **Tradeoffs: accuracy vs latency vs confidence?**

   * Chose **sub-second latency**, fallback logic if confidence low, margin protected pricing.

3. **How does the system learn?**

   * Feedback loops refine confidence scoring, VAT/margin rules adjust dynamically.

4. **How to integrate real-time supplier APIs?**

   * Supplier API ingestion pipeline, scheduled updates into pgvector, freshness via `updated_at`.

5. **If quote rejected, log 3 signals:**

   * Material mismatch (semantic drift).
   * Regional price anomaly.
   * Confidence score miscalibration.

---

### How to Run

```bash
git clone https://github.com/ShubhanshuJha/donizo-material-scraper.git
cd donizo-semantic-pricing
pip install -r requirements.txt
```

* Start PostgreSQL with `pgvector` enabled.
* Ingest dataset (CSV/JSON provided in `data/`).
* Run API server:

```bash
uvicorn app.main:app --reload
```

* Test endpoints with Postman or curl (`tests/` includes samples).

---

### Bonus Features (Planned/Optional)

* Multi-language embeddings fallback.
* Query caching + async workers.
* Confidence vs accuracy curve logging.
* Region-specific pricing multipliers.
* Versioned quote history.
* JSON Schema validation on input/output.

---
