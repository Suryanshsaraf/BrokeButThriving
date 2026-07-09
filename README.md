# 💸 Broke But Thriving

Welcome to **Broke But Thriving**! 🚀 This is an end-to-end student finance copilot built to help students navigate their finances, log real-time expenses, train predictive machine learning models, and access interactive decision-support tools.

We built this project to turn raw daily financial choices into predictive insights that help young adults thrive, even on a tight budget.

---

## 📂 What This Repository Contains

Here's a quick tour of the directory structure:

*   **`src/brokebutthriving/api`**: Our FastAPI backend handling participant onboarding, expense logging, daily check-ins, simulations, and dataset exports.
*   **`src/brokebutthriving/ml`**: The core intelligence layer containing feature engineering, sequence dataset generators, and multi-task model training scripts.
*   **`frontend`**: An interactive, responsive React + Vite web dashboard to collect real-world student data and visualize finance insights.
*   **`data`**: Local SQLite database storage to collect pilot data.
*   **`artifacts`**: Folder holding trained model outputs, weight checkpoints, and exported datasets.

---

## 🧭 Project Direction

Our system revolves around learning from real, authentic data. Here is the step-by-step pipeline:

1.  **Onboarding:** Gather student budget limits and living-context metadata.
2.  **Tracking:** Collect expenses, cash inflows, and daily emotional or context signals.
3.  **Data Engineering:** Build clean, training-ready time-series datasets.
4.  **Modeling:** Train a multi-task machine learning model to predict spending habits, archetype tendencies, and financial-risk metrics.
5.  **Intervention:** Surface personalized "what-if" budget simulations and interactive coaching in the user interface.

---

## 🛠️ Local Development Guide

Let's get the application running locally on your machine!

### 1. Setting Up the Backend 🐍
Initialize a virtual environment, install the project in editable development mode, and start the API server:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
bbt-api
```
*Note: The API server will boot up on `http://127.0.0.1:8000`.*

### 2. Setting Up the Frontend 💻
Navigate to the frontend folder, install npm packages, and run the hot-reloading dev server:

```bash
cd frontend
npm install
npm run dev
```
*Note: The frontend automatically looks for the backend at `http://127.0.0.1:8000/api/v1`. If yours is running elsewhere, override it by setting the `VITE_API_BASE_URL` environment variable.*

---

## 🧠 Model Training & Pipelines

> [!IMPORTANT]
> **No synthetic data here!** We only train models using authentic data collected from the local SQLite database.

Run the following scripts from your activated virtual environment:

```bash
source .venv/bin/activate
# List available public datasets
bbt-fetch-public-data --list

# Export local DB data for training
bbt-export --db-path data/bbt.db --output artifacts/daily_dataset.csv

# Train the main multi-task model
bbt-train --db-path data/bbt.db --output-dir artifacts/run-001

# Train public benchmark models
bbt-train-public-benchmarks --benchmark-dir artifacts/benchmarks --output-dir artifacts/public-benchmark-runs/run-001

# Train sequence-based LSTM spend prediction models
bbt-train-spend-sequences --benchmark-csv artifacts/benchmarks/bls_cex_spend_sequence_benchmark.csv --output-dir artifacts/sequence-runs/run-001
```

### What gets generated during training?
*   **Public Benchmark Trainer:** Generates metrics, respondent splits, saved model weights, and student-subset evaluation files for:
    *   `wellbeing_regression`
    *   `hardship_classification`
    *   `future_difficulty_classification`
*   **BLS Sequence Trainer:** Generates grouped panel splits, baseline comparisons, a real LSTM checkpoint, prediction exports, and young-adult proxy subgroup metrics for next-quarter spend forecasting and high-burn risk.

---

## 📊 Model Intelligence Dashboard

Our backend exposes a trained-model registry endpoint at `GET /api/v1/models/registry`. It reads the latest public benchmark run and BLS sequence run to return:
*   Task-level performance leaderboards
*   Row counts for train, validation, and test sets
*   Feature groups leveraged by each model
*   Subgroup evaluation summaries for young adults and students
*   Explanatory notes distinguishing offline benchmarks from live app scoring

The React frontend consumes this data to render model cards directly next to the student workspace. This displays real, honest benchmark evidence without pretending the public model is already perfectly personalized to their local logs.

---

## 🗄️ Public Datasets

We download and normalize official finance datasets to bootstrap our models:

```bash
source .venv/bin/activate
bbt-fetch-public-data --list
bbt-fetch-public-data --dataset cfpb_mem --dataset cfpb_fwb --dataset fed_shed --dataset bls_cex_interview_recent
bbt-ingest-bls-cex --input-dir data/external/bls_cex_interview_recent --output artifacts/normalized/bls_cex_interview_quarterly.csv
bbt-build-bls-spend-sequences --input-csv artifacts/normalized/bls_cex_interview_quarterly.csv --output artifacts/benchmarks/bls_cex_spend_sequence_benchmark.csv --seq-len 2
bbt-ingest-mem --input-dir data/external/cfpb_mem --output artifacts/normalized/cfpb_mem_normalized.csv
bbt-ingest-fwb --input-csv data/external/cfpb_fwb/cfpb_nfwbs_2016_data.csv --output artifacts/normalized/cfpb_fwb_normalized.csv
bbt-ingest-shed --input-dir data/external/fed_shed --output artifacts/normalized/fed_shed_normalized.csv
bbt-build-public-benchmarks --normalized-dir artifacts/normalized --output-dir artifacts/benchmarks
```

### Normalized Public Tables:
*   `artifacts/normalized/fed_shed_normalized.csv`: `117,102` respondent-year rows from 2013-2024.
*   `artifacts/normalized/cfpb_mem_normalized.csv`: `21,839` respondent-wave rows from the CFPB Making Ends Meet study.
*   `artifacts/normalized/cfpb_fwb_normalized.csv`: `6,394` respondent rows from the CFPB Financial Well-Being Survey.
*   `artifacts/normalized/bls_cex_interview_quarterly.csv`: `76,946` quarterly interview rows from the BLS Consumer Expenditure Surveys (2021-2025).

### Unified Benchmark Outputs:
*   `artifacts/benchmarks/public_finance_master.csv`: `145,335` unified sparse rows across all normalized public sources.
*   `artifacts/benchmarks/public_wellbeing_benchmark.csv`: `27,103` rows with real `fwb_score` targets.
*   `artifacts/benchmarks/public_hardship_benchmark.csv`: `128,912` rows with real hardship/strain targets.
*   `artifacts/benchmarks/public_future_difficulty_benchmark.csv`: `4,657` rows with future bill-difficulty labels from MEM.
*   `artifacts/benchmarks/public_student_finance_rows.csv`: `6,389` student-coded rows across SHED, MEM, and FWB.
*   `artifacts/benchmarks/bls_cex_spend_sequence_benchmark.csv`: `21,400` consecutive-quarter spend-sequence samples across `12,890` BLS panels.

> [!NOTE]
> The benchmark builder keeps source tables intact and constructs task-specific tables on top. This avoids pretending the public surveys asked identical questions while still delivering clean, labeled data for robust model validation.
