import asyncio
import logging
import multiprocessing
from datetime import UTC, datetime, timedelta
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database import Evidence, Fact, FactEvidence, Job, Material, MaterialFragment
from app.knowledge_context import lock_content_fact_set
from app.parsers import OcrUnavailable, ParseFailure, ParseResult, parse_material
from app.storage import FileValidationError, resolve_storage_key

JOB_LEASE = timedelta(minutes=5)
LEASE_RENEW_INTERVAL_SECONDS = 60
PARSE_TIMEOUT_SECONDS = 120
MAX_CANDIDATE_FACTS_PER_MATERIAL = 50
LOGGER = logging.getLogger("geo-saas.jobs")

MATERIAL_FACT_CATEGORY = {
    "license": ("identity", "identity.license", "证照与主体信息"),
    "service": ("service", "service.primary", "核心服务"),
    "price": ("price", "price.primary", "价格说明"),
    "team": ("capability", "capability.primary", "团队与能力"),
    "case": ("case", "case.primary", "代表案例"),
    "channel": ("contact", "contact.public", "渠道与联系方式"),
    "other": ("service", None, "资料候选信息"),
}

GEO_TEMPLATE_FACTS = {
    "企业或机构标准名称": ("identity", "identity.standard_name", "企业标准名称"),
    "对外简称 / 品牌名": ("identity", "identity.brand_name", "品牌名称"),
    "所属行业 / 主营类别": ("identity", "identity.industry", "所属行业"),
    "所在省、市、区县": ("location", "location.administrative_area", "所在地区"),
    "详细地址 / 门店地址": ("location", "location.address", "经营地址"),
    "成立时间": ("identity", "identity.founded_at", "成立时间"),
    "企业一句话介绍": ("identity", "identity.introduction", "企业介绍"),
    "核心服务或产品": ("service", "service.primary", "核心服务"),
    "各项服务详细介绍": ("service", "service.details", "服务详细介绍"),
    "主要服务对象": ("audience", "audience.primary", "主要服务对象"),
    "服务区域 / 上门范围": ("location", "location.service_area", "服务区域"),
    "服务方式": ("service", "service.delivery_mode", "服务方式"),
    "价格或收费方式": ("price", "price.primary", "价格或收费方式"),
    "服务流程": ("process", "process.primary", "服务流程"),
    "营业时间": ("contact", "contact.business_hours", "营业时间"),
    "希望重点推广的服务": ("service", "service.promotion_focus", "重点推广服务"),
    "企业主要优势或特色": ("capability", "capability.primary", "企业优势"),
    "团队情况": ("capability", "capability.team", "团队情况"),
    "真实案例或代表成果": ("case", "case.primary", "真实案例或成果"),
    "客户经常咨询的问题": ("audience", "audience.questions", "客户常见问题"),
    "联系电话": ("contact", "contact.public", "联系电话"),
    "联系微信": ("contact", "contact.wechat", "联系微信"),
    "其他补充说明": ("restriction", "restriction.primary", "其他补充说明"),
}


def _template_fact_content(text: str) -> tuple[str, str, str, str] | None:
    raw_label, separator, raw_value = text.partition(":")
    if not separator:
        return None
    definition = GEO_TEMPLATE_FACTS.get(raw_label.strip())
    value = raw_value.strip()
    if definition is None or not value:
        return None
    category, key, label = definition
    return category, key, label, value[:20_000]


def _candidate_fact_content(
    material: Material,
    text: str,
    position: int,
    occupied_keys: set[str],
    *,
    extraction_method: str,
) -> tuple[str, str, str, str] | None:
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip()).strip()
    if not normalized:
        return None
    if extraction_method == "geo_template":
        return _template_fact_content(normalized)
    category, primary_key, fallback_label = MATERIAL_FACT_CATEGORY.get(
        material.category,
        MATERIAL_FACT_CATEGORY["other"],
    )
    key = (
        primary_key
        if position == 0 and primary_key and primary_key not in occupied_keys
        else f"material.{material.id.hex}.candidate.{position + 1}"
    )
    first_line, _, remaining = normalized.partition("\n")
    label = f"{fallback_label} {position + 1}"
    value = normalized[:20_000]
    for separator in (chr(0xFF1A), ":"):
        if separator in first_line:
            possible_label, possible_value = first_line.split(separator, maxsplit=1)
            if 1 <= len(possible_label.strip()) <= 60 and possible_value.strip():
                label = possible_label.strip()
                value = "\n".join(part for part in (possible_value.strip(), remaining) if part)[
                    :20_000
                ]
                break
    return category, key, label[:200], value


def _parse_process_entry(
    path: str,
    media_type: str,
    output: Connection,
) -> None:
    try:
        output.send(("ok", parse_material(Path(path), media_type)))
    except OcrUnavailable as error:
        output.send(("ocr_unavailable", str(error)))
    except ParseFailure as error:
        output.send(("parse_failure", str(error)))
    except Exception:
        output.send(("unexpected_failure", "资料解析进程异常"))
    finally:
        output.close()


async def _stop_parse_process(process: BaseProcess) -> None:
    if process.is_alive():
        process.terminate()
        await asyncio.to_thread(process.join, 5)
    if process.is_alive():
        process.kill()
        await asyncio.to_thread(process.join, 5)


async def claim_next_job(
    session_factory: async_sessionmaker[AsyncSession],
) -> Job | None:
    now = datetime.now(UTC)
    async with session_factory() as database:
        async with database.begin():
            exhausted = await database.scalars(
                select(Job)
                .where(
                    Job.attempts >= Job.max_attempts,
                    or_(
                        Job.status == "queued",
                        (Job.status == "running")
                        & or_(Job.lease_until.is_(None), Job.lease_until < now),
                    ),
                )
                .with_for_update(skip_locked=True)
                .limit(100),
            )
            for expired in exhausted.all():
                expired.status = "failed"
                expired.progress = 100
                expired.error_message = "任务重试次数已用尽"
                expired.lease_until = None
                expired.completed_at = now
                material = (
                    await database.get(Material, expired.material_id)
                    if expired.material_id
                    else None
                )
                if material is not None:
                    material.extraction_status = "failed"
                    material.extraction_error = expired.error_message
                    material.version += 1
            job = await database.scalar(
                select(Job)
                .where(
                    Job.job_type.in_(
                        (
                            "material_extract",
                            "diagnostic",
                            "strategy_generate",
                            "document_operation",
                            "content_publish",
                            "channel_recommend",
                            "monitoring_batch",
                        ),
                    ),
                    Job.attempts < Job.max_attempts,
                    or_(
                        Job.status == "queued",
                        (Job.status == "running")
                        & or_(Job.lease_until.is_(None), Job.lease_until < now),
                    ),
                )
                .order_by(Job.created_at, Job.id)
                .with_for_update(skip_locked=True)
                .limit(1),
            )
            if job is None:
                return None
            job.status = "running"
            job.attempts += 1
            job.started_at = job.started_at or now
            job.lease_until = now + JOB_LEASE
            job.error_message = None
        database.expunge(job)
        return job


async def _mark_terminal_failure(
    session_factory: async_sessionmaker[AsyncSession],
    job_id: UUID,
    expected_attempt: int,
    message: str,
) -> bool:
    now = datetime.now(UTC)
    async with session_factory() as database:
        async with database.begin():
            job = await database.scalar(
                select(Job)
                .where(
                    Job.id == job_id,
                    Job.status == "running",
                    Job.attempts == expected_attempt,
                )
                .with_for_update(),
            )
            if job is None:
                return False
            material = await database.get(Material, job.material_id) if job.material_id else None
            job.status = "failed"
            job.progress = 100
            job.error_message = message[:500]
            job.lease_until = None
            job.completed_at = now
            if material is not None:
                material.extraction_status = "failed"
                material.extraction_error = message[:500]
                material.version += 1
        return True


async def _requeue_or_fail(
    session_factory: async_sessionmaker[AsyncSession],
    job_id: UUID,
    expected_attempt: int,
    message: str,
) -> bool:
    now = datetime.now(UTC)
    async with session_factory() as database:
        async with database.begin():
            job = await database.scalar(
                select(Job)
                .where(
                    Job.id == job_id,
                    Job.status == "running",
                    Job.attempts == expected_attempt,
                    Job.lease_until >= now,
                )
                .with_for_update(),
            )
            if job is None:
                return False
            if job.attempts < job.max_attempts:
                job.status = "queued"
                job.error_message = message[:500]
                job.lease_until = None
                job.progress = 0
                return True
            job.status = "failed"
            job.progress = 100
            job.error_message = message[:500]
            job.lease_until = None
            job.completed_at = now
            material = await database.get(Material, job.material_id) if job.material_id else None
            if material is not None:
                material.extraction_status = "failed"
                material.extraction_error = message[:500]
                material.version += 1
        return True


async def _persist_parse_result(
    session_factory: async_sessionmaker[AsyncSession],
    claimed_job: Job,
    parsed: ParseResult,
) -> bool:
    now = datetime.now(UTC)
    async with session_factory() as database:
        async with database.begin():
            current_job = await database.scalar(
                select(Job)
                .where(
                    Job.id == claimed_job.id,
                    Job.status == "running",
                    Job.attempts == claimed_job.attempts,
                    Job.lease_until >= now,
                )
                .with_for_update(),
            )
            if current_job is None or current_job.material_id is None:
                return False
            material = await database.get(Material, current_job.material_id)
            if material is None:
                current_job.status = "failed"
                current_job.progress = 100
                current_job.error_message = "资料不存在"
                current_job.lease_until = None
                current_job.completed_at = now
                return True
            await lock_content_fact_set(database, material.client_id)
            await database.execute(
                delete(MaterialFragment).where(MaterialFragment.material_id == material.id),
            )
            fragments = [
                MaterialFragment(
                    id=uuid4(),
                    material_id=material.id,
                    page=fragment.page,
                    text=fragment.text,
                    extraction_method=fragment.extraction_method,
                    sensitivity_tags=list(fragment.sensitivity_tags),
                    position=index,
                )
                for index, fragment in enumerate(parsed.fragments)
            ]
            database.add_all(fragments)
            locked_facts = (
                await database.scalars(
                    select(Fact).where(Fact.client_id == material.client_id).with_for_update(),
                )
            ).all()
            existing_facts = {fact.key: fact for fact in locked_facts}
            occupied_keys = set(existing_facts)
            existing_material_keys = set(
                (
                    await database.scalars(
                        select(Fact.key)
                        .join(FactEvidence, FactEvidence.fact_id == Fact.id)
                        .join(Evidence, Evidence.id == FactEvidence.evidence_id)
                        .where(
                            Fact.client_id == material.client_id,
                            Evidence.material_id == material.id,
                            Evidence.source_type == "material",
                        ),
                    )
                ).all(),
            )
            for index, fragment in enumerate(
                parsed.fragments[:MAX_CANDIDATE_FACTS_PER_MATERIAL],
            ):
                candidate = _candidate_fact_content(
                    material,
                    fragment.text,
                    index,
                    occupied_keys - existing_material_keys,
                    extraction_method=fragment.extraction_method,
                )
                if candidate is None:
                    continue
                category, key, label, value = candidate
                existing_fact = existing_facts.get(key)
                if existing_fact is not None and fragment.extraction_method != "geo_template":
                    continue
                if existing_fact is None:
                    fact = Fact(
                        id=uuid4(),
                        client_id=material.client_id,
                        category=category,
                        key=key,
                        label=label,
                        value=value,
                        status="client_provided",
                        confidence=90 if fragment.extraction_method == "geo_template" else 55,
                    )
                    existing_facts[key] = fact
                else:
                    fact = existing_fact
                    fact.category = category
                    fact.label = label
                    fact.value = value
                    fact.status = "client_provided"
                    fact.confidence = 90
                    fact.valid_from = None
                    fact.valid_until = None
                    fact.confirmation_note = None
                    fact.version += 1
                    await database.execute(
                        delete(FactEvidence).where(FactEvidence.fact_id == fact.id),
                    )
                evidence = Evidence(
                    id=uuid4(),
                    client_id=material.client_id,
                    material_id=material.id,
                    source_type="material",
                    source_label=f"{material.file_name} · 解析片段 {index + 1}",
                    quote=value,
                    observed_at=material.uploaded_at.date(),
                    authorization_status=material.authorization_status,
                )
                database.add_all(
                    [
                        fact,
                        evidence,
                        FactEvidence(fact_id=fact.id, evidence_id=evidence.id),
                    ],
                )
                occupied_keys.add(key)
            material.extraction_status = "succeeded"
            material.extraction_error = None
            material.page_count = parsed.page_count
            material.fragment_count = len(parsed.fragments)
            material.version += 1
            current_job.status = "succeeded"
            current_job.progress = 100
            current_job.lease_until = None
            current_job.completed_at = now
        return True


async def _renew_job_lease(
    session_factory: async_sessionmaker[AsyncSession],
    claimed_job: Job,
) -> bool:
    now = datetime.now(UTC)
    async with session_factory() as database:
        async with database.begin():
            current = await database.scalar(
                select(Job)
                .where(
                    Job.id == claimed_job.id,
                    Job.status == "running",
                    Job.attempts == claimed_job.attempts,
                    Job.lease_until >= now,
                )
                .with_for_update(),
            )
            if current is None:
                return False
            current.lease_until = now + JOB_LEASE
        return True


async def _parse_with_lease_renewal(
    session_factory: async_sessionmaker[AsyncSession],
    claimed_job: Job,
    path: Path,
    media_type: str,
) -> ParseResult:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_parse_process_entry,
        args=(str(path), media_type, sender),
        daemon=True,
    )
    process.start()
    sender.close()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + PARSE_TIMEOUT_SECONDS
    next_renewal = loop.time() + LEASE_RENEW_INTERVAL_SECONDS
    result_message: tuple[str, object] | None = None
    try:
        while True:
            if receiver.poll():
                result_message = receiver.recv()
                break
            if not process.is_alive():
                break
            now = loop.time()
            if now >= deadline:
                await _stop_parse_process(process)
                raise ParseFailure("资料解析超过安全时限")
            if now >= next_renewal:
                if not await _renew_job_lease(session_factory, claimed_job):
                    await _stop_parse_process(process)
                    raise ParseFailure("资料解析任务租约已失效")
                next_renewal = now + LEASE_RENEW_INTERVAL_SECONDS
            await asyncio.sleep(0.1)
        await asyncio.to_thread(process.join, 1)
        if result_message is None and receiver.poll():
            result_message = receiver.recv()
        if result_message is None:
            raise ParseFailure("资料解析进程异常退出")
        status, payload = result_message
        if status == "ok" and isinstance(payload, ParseResult):
            return payload
        if status == "ocr_unavailable":
            raise OcrUnavailable(str(payload))
        raise ParseFailure(str(payload))
    finally:
        await _stop_parse_process(process)
        receiver.close()


async def process_one_job(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> bool:
    job = await claim_next_job(session_factory)
    if job is None:
        return False
    try:
        if job.job_type == "diagnostic":
            from app.strategy import process_diagnostic_job

            return await process_diagnostic_job(session_factory, job, settings)
        if job.job_type == "strategy_generate":
            if job.payload.get("mode") == "keyword_generation":
                from app.keyword_workspace import process_keyword_generation_job

                return await process_keyword_generation_job(
                    session_factory,
                    job,
                    settings,
                )
            from app.strategy import process_strategy_job

            return await process_strategy_job(session_factory, job, settings)
        if job.job_type == "document_operation":
            from app.content import process_content_job

            return await process_content_job(session_factory, job, settings)
        if job.job_type == "content_publish":
            from app.publishing import process_publication_job

            return await process_publication_job(session_factory, job, settings)
        if job.job_type == "channel_recommend":
            from app.channels import process_channel_job

            return await process_channel_job(session_factory, job)
        if job.job_type == "monitoring_batch":
            from app.monitoring import process_monitoring_job

            return await process_monitoring_job(session_factory, job, settings)
    except Exception:
        LOGGER.exception(
            "job_processing_failed",
            extra={"event": "job_processing_failed"},
        )
        await _mark_terminal_failure(
            session_factory,
            job.id,
            job.attempts,
            "任务处理异常，请稍后重试",
        )
        return True
    if job.material_id is None:
        await _mark_terminal_failure(
            session_factory,
            job.id,
            job.attempts,
            "解析任务缺少资料",
        )
        return True
    async with session_factory() as database:
        material = await database.get(Material, job.material_id)
        if material is None:
            await _mark_terminal_failure(
                session_factory,
                job.id,
                job.attempts,
                "资料不存在",
            )
            return True
        material.extraction_status = "running"
        material.extraction_error = None
        material.version += 1
        await database.commit()
        storage_key = material.storage_key
        media_type = material.media_type
    try:
        path = resolve_storage_key(settings.storage_root, storage_key)
        if not path.is_file():
            raise ParseFailure("原始资料文件不存在")
        parsed = await _parse_with_lease_renewal(
            session_factory,
            job,
            path,
            media_type,
        )
    except (OcrUnavailable, FileValidationError) as error:
        await _mark_terminal_failure(
            session_factory,
            job.id,
            job.attempts,
            str(error),
        )
        return True
    except ParseFailure as error:
        await _mark_terminal_failure(
            session_factory,
            job.id,
            job.attempts,
            str(error),
        )
        return True
    except Exception as error:
        await _requeue_or_fail(
            session_factory,
            job.id,
            job.attempts,
            f"资料解析暂时失败: {type(error).__name__}",
        )
        return True

    await _persist_parse_result(session_factory, job, parsed)
    return True
