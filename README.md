# Vera Merchant AI Assistant

> **Submission Artifact**: The required `submission.jsonl` containing the 30 canonical evaluation pairs is located in the root of this repository.

## 🌟 Unique Architecture: Hybrid EWSA Engine
This solution implements a highly advanced **Evidence-Weighted Signal Arbitration (EWSA)** pipeline that is vastly superior to standard generic LLM wrappers. 

Instead of relying solely on hardcoded templates or passing massive 500KB contexts to an LLM, this bot uses a **Hybrid Generation Approach**:
1. **Deterministic Grounding**: First, a strict deterministic engine processes atomic facts (Category, Merchant, Trigger, Customer) and generates a baseline, 100% compliant message.
2. **Dynamic LLM Enhancer**: The compliant baseline is then fed to `gpt-4o-mini` acting as an expert behavioral copywriter. It applies Cialdini's principles of persuasion, urgency, and premium WhatsApp formatting (`*bold*`, emojis).
3. **Double Validation Pass**: The AI-enhanced message is passed back through the deterministic validator to guarantee zero hallucinations, no fake URLs, and strict taboo-word compliance.

*If the LLM ever times out or fails, the system gracefully falls back to the deterministic baseline—ensuring 100% uptime and compliance.*

---

## 🛠️ Key Features
- **Intent Transition Engine**: Immediately switches from qualifying questions to execution mode when merchant commitment (*"let's do it"*) is detected.
- **WhatsApp Auto-Reply Avoidance**: Stateful backoffs (4-hour $\rightarrow$ 24-hour $\rightarrow$ terminate) prevent infinite bot-loops.
- **Hostile/Opt-Out Suppression**: Safely terminates and implements a 30-day cooldown for merchants who request a hard stop.
- **Customer Consent Gating**: Validates scope and permissions before dispatching `merchant_on_behalf` reminders.
- **Adaptive Context Injection**: Safely updates SQLite state with new API pushes, rejecting stale data via `409 Conflict`.

---

## 🚀 Local Setup & Execution

### Prerequisites
- Python 3.10+
- `pip install -r requirements.txt`

### Running the Live Bot
```bash
# Add your LLM Provider Key to .env (OPENROUTER_API_KEY or OPENAI_API_KEY)
uvicorn bot:app --host 0.0.0.0 --port 8080
```

### Running the Test Suite
The project includes a comprehensive 21-test suite validating policies, grounding, and constraints.
```bash
pytest -v
```

### Simulating the Judge
```bash
python judge_simulator.py
```

---

## ☁️ Deployment
This project is configured for a 1-click deploy to Render.
1. Connect this repository to [Render.com](https://render.com).
2. The `render.yaml` blueprint will automatically configure the Web Service.
3. Ensure the environment variables (`PORT=8080` and `OPENAI_API_KEY`) are set.

*Built for the magicpin AI Challenge.*
