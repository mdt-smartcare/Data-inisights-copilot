"""
Agent Definition Generator — AI-bootstrapped Step 4.5.

Reads the selected schema + foreign-key graph + PHI-redacted sample values
from the agent's data source, then calls an LLM to populate an
`AgentDefinition` JSON blob.

The generator is invoked as a background task on data-dictionary-step save
so the user lands on Step 4.5 with the form pre-filled. Failures are logged
and surface as `agent_definition_status = 'failed'` — the wizard then shows
an empty form with a retry affordance.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.logging import get_logger
from app.core.utils.phi_redactor import PHIRedactor
from app.modules.chat.query.schema_graph import SchemaGraph
from app.modules.chat.llm_helper import LLMHelper

logger = get_logger(__name__)

PROMPT_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "core" / "config" / "agent_definition_prompt.md"
)

MAX_SAMPLE_VALUES_PER_COLUMN = 10
MAX_TABLES_FOR_BOOTSTRAP = 40
MAX_PROMPT_TOKENS_ESTIMATE = 12000


class BootstrapError(Exception):
    """Raised when bootstrap cannot complete."""


def _invalidate_fast_sql_cache(agent_id: str) -> None:
    """Invalidate FastSQL cache for an agent when definition changes."""
    try:
        from app.modules.chat.query.fast_sql_service import IntegratedFastSQLServiceFactory
        if agent_id in IntegratedFastSQLServiceFactory._cache:
            del IntegratedFastSQLServiceFactory._cache[agent_id]
            logger.info(f"FastSQL cache invalidated for agent {agent_id}")
    except ImportError:
        pass  # FastSQL not available
    except Exception as e:
        logger.warning(f"Failed to invalidate FastSQL cache: {e}")


def _safe_engine(db_url: str):
    return create_engine(db_url, pool_pre_ping=True, pool_size=1)


def _build_schema_block(
    graph: SchemaGraph,
    tables: List[str],
    selected_columns_map: Dict[str, List[str]],
) -> str:
    """Render schema block as `- table: col1, col2, ...` lines."""
    lines: List[str] = []
    for table in tables:
        info = graph.get_table(table)
        if info is None:
            continue
        cols = selected_columns_map.get(table) or [c.name for c in info.columns]
        cols = cols[:60]
        lines.append(f"- {table}: {', '.join(cols)}")
    return "\n".join(lines) if lines else "(none)"


def _build_fk_block(graph: SchemaGraph, tables: List[str]) -> str:
    """Render FK graph as `from.col -> to.col` lines for the selected scope."""
    table_set = set(tables)
    seen = set()
    lines: List[str] = []
    for fk in graph._foreign_keys:  # noqa: SLF001 — module-internal access acceptable
        if fk.source_table not in table_set:
            continue
        key = (fk.source_table, fk.source_column, fk.target_table, fk.target_column)
        if key in seen:
            continue
        seen.add(key)
        lines.append(
            f"- {fk.source_table}.{fk.source_column} -> {fk.target_table}.{fk.target_column}"
        )
    return "\n".join(lines) if lines else "(no foreign-key relationships detected)"


def _build_sample_values_block(
    graph: SchemaGraph,
    tables: List[str],
    redactor: PHIRedactor,
) -> str:
    """
    Sample distinct values for low-cardinality columns and emit a
    PHI-redacted block. Aborts early when token budget approaches.
    """
    lines: List[str] = []
    char_budget = MAX_PROMPT_TOKENS_ESTIMATE * 4
    chars_used = 0

    for table in tables:
        try:
            samples = graph.sample_distinct_values_for_table(table)
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(f"Failed to sample values for {table}: {exc}")
            continue
        if not samples:
            continue
        for col, vals in samples.items():
            if not vals:
                continue
            trimmed = vals[:MAX_SAMPLE_VALUES_PER_COLUMN]
            joined = ", ".join(str(v) for v in trimmed)
            redacted = redactor.redact(joined).redacted_text if redactor.enabled else joined
            line = f"- {table}.{col}: {redacted}"
            chars_used += len(line)
            if chars_used > char_budget:
                lines.append("- (sample values truncated to fit prompt budget)")
                return "\n".join(lines)
            lines.append(line)
    return "\n".join(lines) if lines else "(no sample categorical values available)"


def _render_prompt(
    agent_name: str,
    schema_block: str,
    fk_block: str,
    sample_values_block: str,
    data_dictionary_block: str,
) -> str:
    """
    Render the prompt template via plain string replace.

    `.format()` is intentionally avoided because the template contains literal
    `{` / `}` (the example JSON shape the LLM must mimic), which break
    `.format()` with `KeyError`.
    """
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{agent_name}", agent_name)
        .replace("{schema_block}", schema_block)
        .replace("{fk_block}", fk_block)
        .replace("{sample_values_block}", sample_values_block)
        .replace("{data_dictionary_block}", data_dictionary_block)
    )


def _build_schema_blocks_sync(
    db_url: str,
    tables: List[str],
    selected_columns_map: Dict[str, List[str]],
) -> Tuple[str, str, str]:
    """
    Synchronous helper that creates SchemaGraph and builds schema/fk/sample blocks.
    
    This is designed to be called via asyncio.to_thread() to avoid blocking
    the event loop during schema reflection and sample value queries.
    """
    engine = _safe_engine(db_url)
    try:
        graph = SchemaGraph(engine, schema_name="public")
        redactor = PHIRedactor(enabled=True, log_redactions=False)
        
        schema_block = _build_schema_block(graph, tables, selected_columns_map)
        fk_block = _build_fk_block(graph, tables)
        sample_values_block = _build_sample_values_block(graph, tables, redactor)
        
        return schema_block, fk_block, sample_values_block
    finally:
        engine.dispose()


_JSON_CODEFENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> Dict[str, Any]:
    """Extract JSON object from LLM output, tolerating code fences."""
    match = _JSON_CODEFENCE.search(text)
    candidate = match.group(1) if match else None
    if candidate is None:
        match = _JSON_OBJECT.search(text)
        candidate = match.group(0) if match else None
    if candidate is None:
        raise BootstrapError("LLM did not return a JSON object")
    return json.loads(candidate)


async def _invoke_llm_for_definition(llm_helper: LLMHelper, prompt: str) -> Dict[str, Any]:
    """Call the LLM with one retry on JSON parse failure."""
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = await llm_helper.get_llm(temperature=0.3, phi_protection=True)

    for attempt in (1, 2):
        try:
            messages = [
                SystemMessage(content="You output only strict JSON. No prose, no markdown fences."),
                HumanMessage(content=prompt),
            ]
            response = await llm.ainvoke(messages)
            raw = response.content if hasattr(response, "content") else str(response)
            return _extract_json(raw)
        except (json.JSONDecodeError, BootstrapError) as exc:
            logger.warning(f"AgentDefinition LLM parse attempt {attempt} failed: {exc}")
            if attempt == 2:
                raise BootstrapError(f"LLM output not parseable as JSON after 2 attempts: {exc}")
    raise BootstrapError("Unreachable: LLM retry loop exited without value")


def _coerce_definition_shape(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure all required keys exist + types are well-formed."""
    defaults: Dict[str, Any] = {
        "role": "",
        "responsibilities": [],
        "business_objectives": [],
        "target_personas": [],
        "analytical_capabilities": [],
        "limitations": [],
        "response_style": {},
        "kpis_metrics": [],
        "domain_rules": [],
        "guardrails": [],
        "sample_questions": [],
        "confidence_per_field": {},
    }
    out = dict(defaults)
    out.update({k: v for k, v in raw.items() if k in defaults})

    normalised_q: List[Dict[str, Any]] = []
    for q in out.get("sample_questions") or []:
        if isinstance(q, str):
            normalised_q.append({"question": q, "use_as_few_shot": True})
        elif isinstance(q, dict) and q.get("question"):
            normalised_q.append({
                "question": q["question"],
                "sql": q.get("sql"),
                "expected_summary": q.get("expected_summary"),
                "use_as_few_shot": q.get("use_as_few_shot", True),
            })
    out["sample_questions"] = normalised_q

    out["ai_drafted_fields"] = [
        k for k in defaults if k != "confidence_per_field" and out.get(k)
    ]
    return out


def _parse_selected_columns(raw: Optional[str]) -> Dict[str, List[str]]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def bootstrap_agent_definition(version_id: int, session: AsyncSession) -> Dict[str, Any]:
    """
    Bootstrap an AgentDefinition for the given agent_config version.

    Persists `agent_definition` JSON + updates `agent_definition_status`.
    
    IMPORTANT: This function uses short transaction scopes to avoid blocking
    other database operations during long-running LLM calls.
    """
    logger.info(f"[BOOTSTRAP] Entered bootstrap_agent_definition for version_id={version_id}")
    from app.modules.agents.models import AgentConfigModel, AgentModel
    from app.modules.data_sources.models import DataSourceModel

    # ========== PHASE 1: Atomically CLAIM the bootstrap slot ==========
    # Single UPDATE statement collapses the SELECT + UPDATE + commit dance so
    # concurrent workers cannot race past each other. The RETURNING clause lets
    # us tell whether we won the claim. Statement only matches rows that are
    # in a re-triggerable state ('not_started' or 'failed'); rows already
    # 'pending' or 'completed' are left alone.
    from sqlalchemy import update as sa_update
    logger.info(f"[BOOTSTRAP] P1.1 atomic CLAIM update for version_id={version_id}")
    # Hard timeout so an orphaned upstream transaction holding the row lock
    # cannot stall the bootstrap forever. If we hit the timeout, raise so the
    # outer error path marks the row as failed and releases the connection.
    try:
        claim_result = await asyncio.wait_for(
            session.execute(
                sa_update(AgentConfigModel)
                .where(AgentConfigModel.id == version_id)
                .where(AgentConfigModel.agent_definition_status.in_(["not_started", "failed"]))
                .values(agent_definition_status="pending")
                .returning(AgentConfigModel.id)
            ),
            timeout=15.0,
        )
        claimed = claim_result.scalar_one_or_none()
        await asyncio.wait_for(session.commit(), timeout=10.0)
    except asyncio.TimeoutError:
        logger.error(
            f"[BOOTSTRAP] CLAIM timed out for version_id={version_id}. "
            f"Likely a stale transaction holds the row lock. Aborting; "
            f"caller must terminate idle-in-transaction backends in pg_stat_activity."
        )
        await session.rollback()
        raise BootstrapError(
            f"CLAIM timed out for version_id={version_id} — DB row 44 is locked by an orphaned transaction"
        )
    logger.info(f"[BOOTSTRAP] P1.2 claim result for version_id={version_id}: claimed={claimed is not None}")

    # Now re-read to see what the current status is.
    result = await session.execute(
        select(AgentConfigModel).where(AgentConfigModel.id == version_id)
    )
    config: Optional[AgentConfigModel] = result.scalar_one_or_none()
    logger.info(
        f"[BOOTSTRAP] P1.3 GOT CONFIG version_id={version_id} "
        f"status={config.agent_definition_status if config else 'None'} "
        f"claimed_by_us={claimed is not None}"
    )
    if config is None:
        raise BootstrapError(f"agent_config version {version_id} not found")

    # If we did not win the claim, somebody else is already running the
    # bootstrap (or it is already completed). Short-circuit without touching
    # the row again so we never pile concurrent UPDATEs onto the same row.
    if claimed is None:
        if config.agent_definition_status == "completed" and config.agent_definition:
            logger.info(f"Bootstrap already completed for version_id={version_id}, returning existing definition")
            return json.loads(config.agent_definition) if isinstance(config.agent_definition, str) else config.agent_definition
        logger.warning(
            f"Bootstrap claim lost for version_id={version_id} "
            f"(another worker is running, status={config.agent_definition_status}). Skipping."
        )
        return {}

    # We are the claimant; status is already 'pending' on disk after the
    # atomic CLAIM commit above. Capture the fields we need for Phase 2/3.
    logger.info(f"[BOOTSTRAP] P1.4 capturing fields from config row")
    data_source_id = config.data_source_id
    agent_id = config.agent_id
    selected_columns_raw = config.selected_columns
    data_dictionary_raw = config.data_dictionary
    logger.info(
        f"[BOOTSTRAP] P1.5 fields captured "
        f"selected_columns_size={len(selected_columns_raw or '') if isinstance(selected_columns_raw, str) else 'non-str'} "
        f"data_dictionary_size={len(data_dictionary_raw or '') if isinstance(data_dictionary_raw, str) else 'non-str'}"
    )

    # ========== PHASE 2: Fetch additional data (short transaction) ==========
    try:
        ds_result = await session.execute(
            select(DataSourceModel).where(DataSourceModel.id == data_source_id)
        )
        data_source: Optional[DataSourceModel] = ds_result.scalar_one_or_none()
        if data_source is None or not data_source.db_url:
            raise BootstrapError("data source missing or has no db_url")
        
        db_url = data_source.db_url  # Capture before releasing

        agent_result = await session.execute(
            select(AgentModel).where(AgentModel.id == agent_id)
        )
        agent_row: Optional[AgentModel] = agent_result.scalar_one_or_none()
        agent_name = agent_row.title if agent_row else "Untitled Agent"

        selected_columns_map = _parse_selected_columns(selected_columns_raw)
        all_table_keys = list(selected_columns_map.keys())
        if not all_table_keys:
            raise BootstrapError("no tables selected for this agent")

        # Deterministic priority sort so bootstrap is reproducible when the
        # selection exceeds MAX_TABLES_FOR_BOOTSTRAP. Production marts use a
        # `_gold` suffix; favor those, then `_silver`, then everything else.
        # Ties resolved alphabetically.
        def _tier(name: str) -> int:
            n = name.lower()
            if n.endswith("_gold") or n.endswith("_gold_part"):
                return 0
            if n.endswith("_silver"):
                return 1
            if n.endswith("_bronze"):
                return 2
            return 3

        sorted_tables = sorted(all_table_keys, key=lambda t: (_tier(t), t.lower()))
        tables = sorted_tables[:MAX_TABLES_FOR_BOOTSTRAP]
        dropped = sorted_tables[MAX_TABLES_FOR_BOOTSTRAP:]
        if dropped:
            logger.warning(
                f"[BOOTSTRAP] selected_columns has {len(all_table_keys)} tables, "
                f"capped at {MAX_TABLES_FOR_BOOTSTRAP}. "
                f"Kept tiers (gold>silver>bronze>other), dropped {len(dropped)} tables. "
                f"First dropped: {dropped[:5]}"
            )

        data_dictionary_block = (data_dictionary_raw or "")[:6000] or "(none provided)"

        # Release the implicit transaction held since the Phase 2 SELECTs so we
        # do not sit idle-in-transaction for the entire LLM call. Without this
        # commit, concurrent PUT /configs/step (e.g. Step 4 Advanced Settings)
        # blocks waiting for this connection's transaction to close.
        await session.commit()
        logger.info("[BOOTSTRAP] Committed after Phase 2 to release connection during LLM call")

        # ========== PHASE 3: Heavy lifting WITHOUT holding transaction ==========
        # Run blocking schema operations in a thread pool
        logger.info(f"[BOOTSTRAP] Building schema blocks for {len(tables)} tables (running in thread pool)...")
        schema_block, fk_block, sample_values_block = await asyncio.to_thread(
            _build_schema_blocks_sync,
            db_url,
            tables,
            selected_columns_map,
        )
        logger.info("[BOOTSTRAP] Schema blocks built successfully")

        prompt = _render_prompt(
            agent_name=agent_name,
            schema_block=schema_block,
            fk_block=fk_block,
            sample_values_block=sample_values_block,
            data_dictionary_block=data_dictionary_block,
        )

        # LLM call - this is the slow part, no transaction held during this
        llm_helper = LLMHelper(db_session=session, agent_id=agent_id)
        raw_definition = await _invoke_llm_for_definition(llm_helper, prompt)
        definition = _coerce_definition_shape(raw_definition)

        # ========== PHASE 4: Save results (short transaction) ==========
        # Re-fetch config to update (avoids stale object issues)
        result = await session.execute(
            select(AgentConfigModel).where(AgentConfigModel.id == version_id)
        )
        config = result.scalar_one_or_none()
        if config is None:
            raise BootstrapError(f"agent_config version {version_id} disappeared during bootstrap")

        config.agent_definition = json.dumps(definition)
        config.agent_definition_status = "completed"
        await session.commit()
        
        # Invalidate FastSQL cache so the new agent_definition takes effect
        _invalidate_fast_sql_cache(str(agent_id))
        
        logger.info(
            f"[BOOTSTRAP] AgentDefinition bootstrapped for version_id={version_id}, "
            f"tables={len(tables)}, sample_questions={len(definition['sample_questions'])}"
        )
        return definition

    except Exception as exc:
        logger.exception(f"[BOOTSTRAP] AgentDefinition bootstrap failed for version_id={version_id}: {exc}")
        try:
            # Re-fetch to update status
            result = await session.execute(
                select(AgentConfigModel).where(AgentConfigModel.id == version_id)
            )
            config = result.scalar_one_or_none()
            if config:
                config.agent_definition_status = "failed"
                await session.commit()
        except Exception:
            await session.rollback()
        raise


async def bootstrap_agent_definition_background(version_id: int) -> None:
    """
    FastAPI BackgroundTasks entry point.

    Opens its own AsyncSession (the request session is closed by the time
    background tasks run) and swallows exceptions so they don't propagate.
    
    NOTE: This MUST be an async function that runs in FastAPI's event loop.
    Using asyncio.run() would create a new event loop, which breaks asyncpg
    connections that are tied to the original loop.
    """
    try:
        from app.core.database.connection import get_database
        from app.modules.agents.models import AgentConfigModel
        from sqlalchemy import select

        logger.info(f"Starting AgentDefinition bootstrap background task for version_id={version_id}")
        
        db = get_database()
        if db is None:
            logger.error(f"Cannot run bootstrap for version_id={version_id}: get_database() returned None")
            return
        if not db.is_connected:
            logger.error(f"Cannot run bootstrap for version_id={version_id}: database not connected")
            return
        
        logger.info(f"Database available, running bootstrap for version_id={version_id}")

        try:
            logger.info(f"Creating database session for bootstrap version_id={version_id}")
            async with db.session() as session:
                logger.info(f"Database session created, calling bootstrap_agent_definition")
                try:
                    result = await bootstrap_agent_definition(version_id, session)
                    logger.info(f"Bootstrap completed successfully for version_id={version_id}")
                except Exception as inner_exc:
                    logger.exception(f"Exception inside bootstrap_agent_definition for version_id={version_id}: {inner_exc}")
                    raise
        except Exception as exc:
            # Inner function already logged the cause + tried to set status=failed.
            # But if the exception happened before setting pending, mark as failed now.
            logger.warning(f"AgentDefinition background task ended with: {exc}")
            try:
                async with db.session() as session:
                    result = await session.execute(
                        select(AgentConfigModel).where(AgentConfigModel.id == version_id)
                    )
                    config = result.scalar_one_or_none()
                    if config and config.agent_definition_status == "not_started":
                        config.agent_definition_status = "failed"
                        await session.commit()
                        logger.info(f"Marked version_id={version_id} as failed after bootstrap error")
            except Exception as update_exc:
                logger.error(f"Failed to mark version_id={version_id} as failed: {update_exc}")
    except Exception as e:
        logger.error(f"Fatal error in bootstrap_agent_definition_background for version_id={version_id}: {e}")
