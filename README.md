# AI Sales & CRM Automation Agent

A CRM (leads, customers, pipeline, tasks, meetings) with an AI agent built on top of it.
Stack: FastAPI, PostgreSQL, Redis, Jinja2 + Bootstrap (no React), LangChain/LangGraph, RAG, MCP, Docker.

## How it fits together

    Browser (Jinja2 pages + Bootstrap + a little JS)
        |
    FastAPI app
      routers/    -> receive requests (pages + /api endpoints)
      services/   -> the real business logic (CRM rules, auth, audit)
      models/     -> database tables (SQLAlchemy)
      schemas/    -> shapes of data going in and out (Pydantic)
      ai/         -> (Phase 3) the AI model switch, prompts, and answer checking (LangChain)
      agent/      -> (Phase 4) the AI assistant: LangGraph workflow, tools, run history
      knowledge/  -> (Phase 5) reading documents, splitting them into passages, keyword + meaning search
                     (Phase 5, remaining) MCP, background work with Redis
        |
    PostgreSQL (all CRM data, audit log)      Redis (cache, background coordination)

Key idea: the AI agent never touches the database directly. It calls the same `services/`
functions the web pages use, so every rule, permission and audit entry applies to AI actions too.

## Project structure

    app/
      main.py            app startup
      core/              settings, database, security, permission checks
      models/            User, AuditLog, Lead, Customer, Interaction, Opportunity, Task
      schemas/           request/response shapes
      services/          lead, customer, opportunity, task, dashboard, user, audit, access (who may see what)
      routers/           API: auth, users, leads, customers, opportunities, tasks
                         Pages: pages (login, dashboard), crm_pages (leads, customers, pipeline, tasks)
      templates/         Jinja2 pages (Bootstrap)
      static/            css, js
    migrations/          Alembic: database changes, one file per change
    scripts/create_admin.py
    tests/
    Dockerfile, docker-compose.yml, .env.example

## AI setup (free)
The AI uses Google's Gemini through LangChain. Google offers a free tier with no credit card.
1. Go to https://aistudio.google.com, sign in, and click "Get API key".
2. Put it in `.env`:  `GOOGLE_API_KEY=your-key`  (then restart the app)
3. Check it works:  `python -m scripts.check_ai`  (with Docker: `docker compose exec app python -m scripts.check_ai`)

Good to know:
- Free tier limits are small (roughly 10-15 requests a minute and a daily cap) and Google changes them. If you hit the limit the app says so; wait a minute.
- On the free tier Google may use what you send to improve its products. Use made-up or non-sensitive data until you move to a paid key.
- Model names change. If you see "model name was not found", copy a current Flash model name from AI Studio into `LLM_MODEL` in `.env`. The default `gemini-flash-latest` follows the newest Flash model.
- You can switch to Claude or GPT later by changing `LLM_PROVIDER`, `LLM_MODEL` and the matching key, and installing `langchain-anthropic` or `langchain-openai`. (Only Gemini was set up for this phase.)

## What Phase 3 added
- Qualify with AI (on a lead): a 0-100 score, a suggested status, strengths, gaps and next steps. It only suggests; you press a button to use the suggested status.
- Follow-up email drafts for leads and customers (friendly, formal or brief, with an optional goal). Customer drafts also use recent history and open deals.
- Email drafts page: read, edit, copy, open in your own email app, or discard. Nothing is sent by the app yet; approvals and sending arrive in Phase 5.
- Safety: the AI only sees records you are allowed to see, text from leads is fenced off as data (not instructions), answers are checked before use, and every AI action is in the audit log.

## What Phase 4 added: the AI Assistant
Open **AI Assistant** in the menu and ask in plain words, for example "Which of my open leads have gone quiet for a week? Tell me what to do about the top three."

How it works: a LangGraph loop where the AI reads your request, chooses tools, sees the results, and repeats until it can answer.
- It can **look up** leads, customers, deals, tasks and the pipeline, **score** a lead, **write email drafts**, and **create tasks** for you.
- It **cannot** send emails, change a lead's status, move a deal, assign work to others, or delete anything. Those need a person (approvals come in Phase 5).
- It acts *as you*: it uses the same permission checks as the rest of the app, so a sales rep's assistant only ever sees that rep's records.
- Text from your data (lead notes and so on) is passed in as information only, never as instructions.
- Every request is saved with a step-by-step list of what the assistant looked at and did, shown under the answer, and recorded in the audit log.

Limits that protect the free AI quota (change them in `.env` if you move to a paid key):

| Setting | Default | Meaning |
|---|---|---|
| AGENT_MAX_STEPS | 6 | most AI "thinking" rounds per request |
| AGENT_MAX_TOOL_CALLS | 12 | most lookups/actions per request |
| AGENT_MAX_AI_ACTIONS | 4 | most scores/email drafts per request |
| AGENT_RUNS_PER_HOUR | 20 | requests per person per hour |

A request waits for the answer (up to about a minute on the free tier). Running it in the background with Redis comes in Phase 5.

Upgrading from Phase 3? Replace the files, then run `pip install -r requirements.txt` and `alembic upgrade head` (Docker does the second step by itself; use `docker compose up --build`).

## What Phase 5 (step 1) added: human approval
The AI can **ask** to do sensitive things, but it can never do them. Each request waits on the **Approvals** page (the menu shows how many are waiting) until a person approves or rejects it.

What can be requested: send a drafted email, change a lead's status, move a deal to another stage.

Safety rules built in (all covered by tests):
- You see exactly what will happen before you decide (for an email: the recipient, subject and full text).
- The recipient is always the address on the draft. The AI cannot choose or change it.
- If the email draft is edited after the request, or the lead/deal changed in the meantime, the approval **fails safely** instead of doing something you did not see.
- An approval runs **at most once**, even with a double click or two people clicking together (tested with 8 simultaneous clicks: one email sent).
- Approving uses the permissions of the person who clicks. A sales rep can only decide their own requests; managers and admins can decide anyone's.
- Everything is in the audit log: requested, approved or rejected (and by whom), executed or failed.
- The AI assistant has no tool to approve anything. Only a person clicking in the app can.

You can also send an email yourself from a draft page (the **Send email** button). That is a person acting directly, so no approval is needed.

### Email sending
By default `EMAIL_BACKEND=console`: sending only writes the email to the server log, and the app says so. Nothing is delivered, so you can try everything safely.
To really send, set in `.env`:

    EMAIL_BACKEND=smtp
    EMAIL_FROM=you@example.com
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=you@gmail.com
    SMTP_PASSWORD=<an app password, not your normal password>

(Gmail needs 2-step verification and an "app password"; check Google's help page for the current steps. Other providers work the same way with their own host and port.) Replies go to the email address of the person who wrote the draft. At most 20 emails per person per hour (`EMAIL_MAX_PER_HOUR`).

Upgrading from Phase 4? Replace the files, then `pip install -r requirements.txt` and `alembic upgrade head` (Docker does the second step itself with `docker compose up --build`).

## What Phase 5 (step 2) added: company knowledge (RAG)
Open **Knowledge** in the menu. Managers and admins add documents (price lists, product sheets, sales playbooks, policies) by uploading a `.pdf`, `.docx`, `.txt` or `.md` file (up to 5 MB), or by pasting text. Everyone can read and search them.

How the AI uses them ("retrieval-augmented generation", RAG): before it answers, it looks up the few passages that matter and reads only those.
- **Scoring a lead** reads your ideal-customer-profile and qualification rules, and the lead card shows which documents it used.
- **Writing an email** can use real prices, offers and product facts from your documents. It is told to use nothing else, and not to mention prices if nothing was found.
- **The AI Assistant** has a "search knowledge" tool for questions like "what does the Team plan cost?", and names the document it used. If nothing relevant is found it says so, and is told never to make facts up.
- The **Try a search** box on the Knowledge page shows exactly which passages come back for a question, so you can check what the AI would see.

Two kinds of search work together:
- **Keyword search** always works, with no setup, and nothing leaves your computer for it.
- **Search by meaning** also finds passages that use different words (a question about "cost" finds a passage about the "fee"). It uses the same free `GOOGLE_API_KEY` and Gemini's embedding model. If you add the key after uploading documents, press **Re-index** on the Knowledge page. If the free limit is reached while adding a document, the document is still saved and searchable by keyword; re-index later.

Safety and limits:
- Document text is treated as information, never as instructions to the AI.
- A search problem never stops the AI from working; it just has no documents to read that time.
- When search by meaning is on, document text is sent to Google to be converted into numbers, and the passages used are included in AI requests. On the free tier Google may use that data to improve its products, so do not upload confidential documents until you move to a paid key. With `KNOWLEDGE_SEMANTIC=false` no document text is sent for embedding (passages are still sent inside AI prompts when used).
- The library holds up to 10,000 passages (about 9 MB of text). Past that, new documents are refused with a clear message instead of quietly becoming unsearchable. Measured on PostgreSQL: a search takes about 0.2 seconds per 1,000 passages (1 s at 5,000; 2 s at 10,000). If you need far more, the next step is a vector database such as the pgvector extension.
- Only the text is stored, not the original file. Scanned (picture-only) PDFs cannot be read; paste the text instead.

Upgrading from the previous step? Replace the files, then `pip install -r requirements.txt` and `alembic upgrade head` (Docker does the second step itself).

## Roles and who sees what
- admin: everything, including creating users
- manager: sees and edits all leads, customers, deals and tasks; can assign leads and tasks to anyone
- sales_rep: sees only their own records; new records they create are automatically theirs

## What Phase 2 added
- Leads: create, edit, search, filter, assign (managers), set status, convert to a customer
- Customers: details, search, and a history of calls, emails, meetings and notes
- Pipeline: deals with stages (prospecting, qualification, proposal, negotiation, won, lost), a board view, totals and win rate
- Tasks: due dates, overdue tracking, can be linked to a lead or customer
- Dashboard with real numbers, scoped to the person logged in
- Every change is written to the audit log
- Every page has an API twin under /api (see /docs in the browser) so the AI agent can use the same logic

## Run with Docker
    cp .env.example .env          # then change SECRET_KEY
    docker compose up --build     # the database is updated automatically on start (alembic upgrade head)
    docker compose exec app python -m scripts.create_admin you@example.com "Your Name" "a-strong-password"
    # open http://localhost:8000

Upgrading from Phase 1? Phase 1 created its tables without migrations, so start the database fresh once:
`docker compose down -v` and then the steps above (this deletes the old test data).

## Run without Docker
Start PostgreSQL, set DATABASE_URL in .env (use localhost), then:
    pip install -r requirements.txt
    alembic upgrade head
    python -m scripts.create_admin you@example.com "Your Name" "a-strong-password"
    uvicorn app.main:app --reload

## Changing the database later
Edit a model in app/models, then:
    alembic revision --autogenerate -m "describe the change"
    alembic upgrade head

## Tests
    python -m pytest -q      # uses an in-memory SQLite database, no PostgreSQL needed
    TEST_DATABASE_URL=postgresql+psycopg2://user:pass@localhost/testdb python -m pytest -q   # same tests on PostgreSQL
(the PostgreSQL test database is emptied by the tests, so never point it at real data)

## Roadmap
1. Foundation (done): login, roles, audit log, Docker, tests
2. Core CRM (done): leads, customers, tasks, pipeline, dashboard numbers, migrations
3. LLM via LangChain (done): lead qualification, follow-up email drafts
4. LangGraph + tool calling (done): the AI assistant for multi-step sales tasks
5. Human approval (done), company knowledge / RAG (done), then MCP and Redis (next)
6. Final testing and deployment
