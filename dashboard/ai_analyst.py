"""AI pricing analyst: Claude answers questions by querying the marts with SQL.

Claude gets one tool, `run_sql`, bound to the read-only sandbox in
sql_sandbox.py. The SDK's tool runner handles the call -> result -> answer loop.
"""

import os

import anthropic
from anthropic import beta_tool

from dashboard.sql_sandbox import UnsafeQueryError, describe_schema, run_query

MODEL = "claude-opus-5-5"
MAX_TOOL_ITERATIONS = 8

SYSTEM_PROMPT = """You are a pricing analyst for an Apple product pricing dashboard.
Answer questions using the run_sql tool against the DuckDB tables below, then give a concise answer
(a few sentences or a short table) that quotes the actual numbers you found.

Context:
- Data: 80,000 Amazon and Flipkart listing snapshots for 31 Apple models, Sep 2020 - Jul 2026, prices in USD.
- price_index = price / launch MSRP x 100 (100 means trading at MSRP).
- "Normal price" means baseline_price_30obs_usd: the mean of the previous 30 non-event observations.
- Forecasts are CatBoost quantile models; P10-P90 is a calibrated 80% range.

Rules:
- Only use the tables listed. Run one SELECT per tool call; results are capped at 200 rows, so aggregate.
- If a question cannot be answered from these tables, say so instead of guessing.
- Mention which table(s) the answer comes from.

Tables:
{schema}"""


def get_api_key(secrets=None) -> str | None:
    if secrets is not None:
        try:
            if "ANTHROPIC_API_KEY" in secrets:
                return secrets["ANTHROPIC_API_KEY"]
        except Exception:  # st.secrets raises when no secrets file exists
            pass
    return os.getenv("ANTHROPIC_API_KEY")


def ask(question: str, history: list[dict], connection, api_key: str) -> dict:
    """Run one analyst turn. Returns {"answer": str, "queries": [(sql, rows | error)]}."""
    executed: list[tuple[str, str]] = []

    @beta_tool
    def run_sql(query: str) -> str:
        """Run a read-only DuckDB SELECT query against the pricing marts and return the result as CSV.

        Args:
            query: A single SELECT (or WITH ... SELECT) statement.
        """
        try:
            result = run_query(connection, query)
        except UnsafeQueryError as error:
            executed.append((query, f"rejected: {error}"))
            return f"Query rejected: {error}"
        except Exception as error:  # SQL errors go back to the model so it can fix the query
            executed.append((query, f"error: {error}"))
            return f"SQL error: {error}"
        executed.append((query, f"{len(result)} rows"))
        return result.to_csv(index=False, float_format="%.4g") if not result.empty else "(no rows)"

    client = anthropic.Anthropic(api_key=api_key)
    system = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT.format(schema=describe_schema(connection)),
            "cache_control": {"type": "ephemeral"},
        }
    ]

    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=16000,
        system=system,
        tools=[run_sql],
        messages=[*history, {"role": "user", "content": question}],
        output_config={"effort": "medium"},
        max_iterations=MAX_TOOL_ITERATIONS,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )

    final = None
    for message in runner:
        final = message

    if final is None:
        return {"answer": "No response was returned.", "queries": executed}
    if final.stop_reason == "refusal":
        return {"answer": "The model declined to answer this question.", "queries": executed}

    answer = "\n".join(block.text for block in final.content if block.type == "text").strip()
    if final.stop_reason == "max_tokens":
        answer += "\n\n_(Answer truncated.)_"
    return {"answer": answer or "No answer was produced.", "queries": executed}


def describe_error(error: Exception) -> str:
    if isinstance(error, anthropic.AuthenticationError):
        return "The Anthropic API key is invalid."
    if isinstance(error, anthropic.RateLimitError):
        return "Rate limited by the Anthropic API - try again in a minute."
    if isinstance(error, anthropic.APIStatusError):
        return f"Anthropic API error ({error.status_code}): {error.message}"
    if isinstance(error, anthropic.APIConnectionError):
        return "Could not reach the Anthropic API."
    return f"Unexpected error: {error}"
