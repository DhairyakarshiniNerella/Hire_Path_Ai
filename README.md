# HirePath AI

**HirePath AI** is a multi-agent Agentic AI job recommendation platform. It analyzes a candidate's resume to understand their skills, experience, education, projects, and career goals, then uses a team of specialized AI agents — coordinated by **LangGraph** — to search live job APIs, analyze job requirements, compare them against the candidate's profile using deterministic scoring and semantic embeddings, identify skill gaps, and generate explainable, personalized job recommendations.

## Why this project exists

Most "AI resume matcher" demos are a single LLM prompt wrapped in a UI. HirePath AI is different: it's built as a genuine **multi-agent system**, where a Supervisor agent orchestrates specialized agents through a shared state graph, each with a distinct responsibility, using real external tools (job search APIs) and a deterministic (non-hallucinated) scoring engine underneath the LLM's natural-language explanations.

## Architecture

```
                    USER
                      |
              HTML / CSS / JavaScript
                      |
                    Flask
                      |
              Supervisor Agent (LangGraph)
                      |
    ┌─────────────┬───────────────┬──────────────┬─────────────┐
    ↓             ↓               ↓               ↓             ↓
Resume       Job Search      Job Analysis     Matching     Recommendation
Analyzer        Agent           Agent           Agent          Agent
Agent            |               |               |              |
    |      ┌──────┼──────┐        |         Deterministic         |
    |      ↓      ↓      ↓        |         Python scoring    LLM explains
    |   Adzuna Jooble Arbeitnow   LLM extracts     +          the results
    |                          requirements    MiniLM (ONNX)     (no score
Groq LLM                       from job text    embeddings      invention)
extracts                       (skills, exp,   for semantic
structured                     education...)    similarity
profile
```

Every agent reads from and writes to one shared `WorkflowState` object. The **Supervisor** doesn't do any work itself — it inspects the state after each agent runs and decides which agent runs next (a classic LangGraph "supervisor pattern"), which is what makes this a real graph rather than a hardcoded pipeline.

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Frontend | HTML, CSS | No framework overhead; `fetch()` talks directly to Flask |
| Backend | Flask (Python) | Simple, well-understood REST API layer |
| Agent Orchestration | LangGraph | Shared state graph, conditional routing between agents |
| LLM Reasoning | LangChain + Groq (`openai/gpt-oss-20b`) | Free, fast inference for structured extraction and explanations |
| Semantic Similarity | `sentence-transformers/all-MiniLM-L6-v2` via `fastembed` (ONNX) | Free, local embeddings — no per-call cost, low enough memory for small hosts |
| Job Data | Adzuna API, Jooble API, Arbeitnow API | Three legitimate, documented, free job sources |
| Resume Parsing | `pypdf`, `python-docx` | Extracts text from PDF/DOCX resumes |
| Data Validation | Pydantic | Enforces structured, type-safe LLM output |

## The Agents

1. **Supervisor Agent** — inspects shared state, decides which agent runs next, and safely halts on errors.
2. **Resume Analyzer Agent** — uses Groq to turn raw resume text into a structured `CandidateProfile` (skills, experience, education, target roles, etc.), with strict "don't invent missing data" instructions.
3. **Job Search Agent** — uses Groq to generate realistic search queries from the candidate's profile, then calls all 3 job APIs as tools.
4. **Job Analysis Agent** — uses Groq to extract each job's real requirements (skills, education, role, technologies, responsibilities) from raw description text.
5. **Matching Agent** — combines skill matching, experience compatibility, semantic role/project similarity, and education relevance into one weighted match score, using **pure deterministic Python** — the LLM never invents this number.
6. **Recommendation Agent** — takes the already-scored, already-ranked jobs and asks Groq to explain *why* each one matches, in plain language, without changing any of the underlying numbers.

## Why deterministic scoring (not LLM-scored)?

LLMs are unreliable at producing consistent, comparable numeric scores. HirePath AI computes the match score with fixed, auditable Python logic — weighted 35% skills / 25% experience / 20% role / 10% projects / 10% education — and only asks the LLM to *narrate* that result. This makes every recommendation explainable and reproducible.

## Experience Compatibility

A dedicated regex-based parser recognizes real-world phrasing ("Fresher", "0-2 years", "3+ years", "Minimum 2 years", etc.) and compares it against the candidate's actual experience, producing one of: **Compatible**, **Low**, **Overqualified**, or **Unknown** — never a guessed number when a job posting doesn't state a clear requirement.

## Project Structure

```
HirePath AI/
├── backend/
│   ├── app/
│   │   ├── main.py                 
│   │   ├── agents/                 # The 6 specialized agents
│   │   ├── tools/                  # Resume parser + job API clients
│   │   ├── services/               # Normalization, dedup, matching, embeddings
│   │   ├── models/                 # Pydantic CandidateProfile model
│   │   └── graph/                  # LangGraph state + workflow definition
│   ├── requirements.txt
│   └── .env                        # API keys (never committed)
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── script.js
├── tests/
└── README.md
```

## Running it locally

**Prerequisites:** Python 3.10+, free API keys for [Groq](https://console.groq.com), [Adzuna](https://developer.adzuna.com), and [Jooble](https://jooble.org/api/about) (Arbeitnow needs no key).

```powershell
# 1. Set up the backend
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Add your API keys
# Create backend/.env with:
#   GROQ_API_KEY=...
#   GROQ_API_KEY_2=...   (optional - a second free Groq key, used as an
#                          automatic fallback once GROQ_API_KEY's daily
#                          quota is exhausted)
#   ADZUNA_APP_ID=...
#   ADZUNA_APP_KEY=...
#   JOOBLE_API_KEY=...

# 3. Run the backend
cd app
python main.py
```

Then open `frontend/index.html` directly in your browser.

## Known Limitations

- Groq's free tier caps usage at 8000 tokens/minute and 200,000 tokens/day, either of which can be hit during heavy testing. The app surfaces this as a clear, friendly error (with an estimated wait time) rather than crashing, and can optionally fall back to a second Groq key (`GROQ_API_KEY_2`) with its own separate quota if one is configured.
- Job analysis is capped to 15 unique jobs per search to control LLM call volume.
- Agent progress in the UI is a simulated visual reveal, not a true real-time stream (no WebSockets/SSE yet — see Future Improvements).

## Future Improvements

- Real-time agent progress via Server-Sent Events or WebSockets
- Persistent storage of past searches/recommendations
- Retry-with-backoff for rate-limited LLM calls
- A 4th/5th job source for broader coverage

## License

This project was built for educational/portfolio purposes.
