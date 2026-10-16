# [AI Evals for Engineers & PMs](https://bit.ly/evals-ai)

**Learn practical, data-driven methods to quickly evaluate and improve AI applications.**

This folder holds my notes for the course. The homework itself lives in the rest of this
repository, a fork of [ai-evals-course/cartwheel-homeworks](https://github.com/ai-evals-course/cartwheel-homeworks).

---

### 🤔 Do you catch yourself asking any of the following questions while building AI applications?

1. How do I test applications when the outputs are stochastic and require subjective judgements?
2. If I change the prompt, how do I know I'm not breaking something else?
3. Where should I focus my engineering efforts? Do I need to test everything?
4. What if I have no data or customers, where do I start?
5. What metrics should I track? What tools should I use? Which models are best?
6. Can I automate testing and evaluation? If so, how do I trust it?

**If you aren't sure about the answers to these questions, this course is for you.**

### 🛠️ What you'll learn

1. Fundamentals & Lifecycle of LLM Evaluation
2. Systematic Error Analysis
3. Implementing Effective Evaluations
4. Collaborative Evaluation Practices
5. Architecture-Specific Strategies
6. Production Monitoring & Continuous Evaluation
7. Efficient Continuous Human Review Systems
8. Cost Optimization Techniques

### 👥 Who should attend?

* Engineers & technical PMs building AI products.
* Developers seeking rigorous evaluation beyond basic prompt tuning.
* Teams aiming to automate and trust their AI testing.

## 👉 [Link to course](https://maven.com/parlance-labs/evals) 👈

### 🔗 Important links

* [Course home page](https://maven.com/parlance-labs/evals/7/home): track progress, course reader, and reading schedule
* [Syllabus](https://docs.google.com/document/d/1KSUlzN-C8z1q_gHduCi6eKgCzlHVV6u3dT0aypqi_YI/edit?tab=t.0)
* [Homework index](../homework/README.md)

> **Note:** Course materials and homework repositories are on GitHub at [ai-evals-course](https://github.com/ai-evals-course).
> The course reader and reading schedule PDFs are course materials and are not committed to this public fork.

---

## Local setup

Run every command from the repository root. Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                          # install dependencies into .venv
uv run python -m seed.generate   # build data/cartwheel.db and the 18 policy docs
cp -n .env.example .env          # then add one provider key (never commit .env)
uv run pytest                    # offline, no API key needed
```

- **Agent model:** a small model, as the course requires, so the agent still makes mistakes to
  study. I use `CARTWHEEL_MODEL=claude-haiku-4-5` with `ANTHROPIC_API_KEY` in `.env`; the
  default is `gpt-4o-mini` with `OPENAI_API_KEY`.
- **Reset the world:** refunds and cancellations change `data/cartwheel.db`. Re-run
  `uv run python -m seed.generate` before a conversation that needs the original state. The
  seed is deterministic, so demo orders 4127, 3980 and 4455 always belong to shopper 1.
- **World date:** the data's "today" is `world_asof` = 2026-07-01 in the `meta` table, not the
  real date.
- **Chat with the agent:**

  ```bash
  uv run python -m agent.cli --role shopper  --user 1    --debug
  uv run python -m agent.cli --role merchant --user 9002 --debug   # store 2
  uv run python -m agent.cli --role support  --user 9501 --debug
  ```

- **Browse the database:** open `data/cartwheel.db` as a SQLite data source in DataGrip or
  the IntelliJ Database panel (set it read-only; refresh after re-seeding).

## Workflow

- One branch and pull request per homework (`hw1`, `hw2`, ...), merged into this fork's
  `main`. Pull requests target this fork, never the upstream course repository.
- Ignored and never committed: `.env`, `data/cartwheel.db`, `.venv/`, `.sessions.db*`, `.idea/`.
