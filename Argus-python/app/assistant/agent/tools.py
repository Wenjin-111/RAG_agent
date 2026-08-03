import json
import logging
from typing import Optional

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

from app.engine.vector_store import PgVectorRetrievalAdapter
from app.qa.retrieval import HybridChunkRetrievalService
from app.config import settings

logger = logging.getLogger(__name__)


def _admin_info(config: RunnableConfig) -> Optional[dict]:
    """返回 {user_id, user_code}，非管理员返回 None。"""
    cfg = (config.get("configurable") or {}) if config else {}
    if cfg.get("system_role") != "ADMIN":
        return None
    user_id = cfg.get("user_id")
    user_code = cfg.get("user_code") or ""
    return {"user_id": user_id, "user_code": user_code}


def _deny() -> str:
    return json.dumps({"ok": False, "message": "无权访问：该操作仅限管理员使用"}, ensure_ascii=False)


async def _confirm_interrupt(action: str, target: str, impact: str) -> str:
    """暂停图执行等待用户确认（human-in-the-loop）。

    interrupt() 在 async 工具中同步调用：langgraph 通过 context 拦截，
    暂停整个图并把确认信息返回前端；用户确认后 resume 恢复执行。
    """
    from langgraph.types import interrupt
    return interrupt({
        "type": "confirmation",
        "action": action,
        "target": target,
        "impact": impact,
        "confirmLabel": "确认执行",
        "cancelLabel": "取消",
    })


@tool
async def knowledge_base_search(query: str, config: RunnableConfig = None) -> str:
    """Search the knowledge base for documents matching the query. Use this when you need to find information from uploaded documents."""

    cfg = config.get("configurable", {}) if config else {}
    result_holder = cfg.get("result_holder")
    group_id = cfg.get("group_id")

    logger.info("KB search tool called: query=%s, group_id=%s", query[:100], group_id)

    if result_holder and getattr(result_holder, "has_completed_search", False):
        return json.dumps({
            "found": False,
            "reasonCode": "DUPLICATE_TOOL_CALL",
            "message": "本轮已经完成过一次知识库检索，请基于上一条工具返回的 evidences 直接给出最终回答。",
            "evidences": None,
            "citations": getattr(result_holder, "current_citations", []),
        }, ensure_ascii=False)

    if not group_id:
        return json.dumps({"found": False, "reasonCode": "NO_GROUP", "message": "未指定知识库群组"})

    vector_adapter = PgVectorRetrievalAdapter(settings.database_url)
    retrieval = HybridChunkRetrievalService(vector_adapter)
    bundle = await retrieval.retrieve(group_id, query, [query])

    citations = []
    evidences = []
    for doc in bundle.documents:
        citations.append({"index": len(citations) + 1, "file_name": doc.source_file})
        evidences.append({"content": doc.content})

    if result_holder:
        result_holder.has_completed_search = True
        result_holder.current_citations = citations

    return json.dumps({
        "found": True,
        "reasonCode": "SUCCESS",
        "evidences": evidences,
        "citations": citations,
    }, ensure_ascii=False)


# ─────────────────────────────────────────────
# 管理助手工具（仅 ADMIN 可用）
# ─────────────────────────────────────────────

def _ok(data: dict) -> str:
    return json.dumps({"ok": True, **data}, ensure_ascii=False, default=str)


@tool
async def list_groups(config: RunnableConfig = None) -> str:
    """List all groups on the platform with member counts. Admin only."""
    if not _admin_info(config):
        return _deny()
    from app.dependencies import async_session_factory
    from app.group.models import Group, GroupMembership
    from sqlalchemy import select, func

    async with async_session_factory() as s:
        rows = (await s.execute(
            select(Group, func.count(GroupMembership.id).label("mc"))
            .outerjoin(GroupMembership, GroupMembership.group_id == Group.id)
            .where(Group.status != "DELETED")
            .group_by(Group.id)
            .order_by(Group.created_at.desc())
        )).all()
        groups = [{
            "groupId": g.id, "groupCode": g.group_code, "groupName": g.group_name,
            "status": g.status, "memberCount": mc,
        } for g, mc in rows]
    return _ok({"count": len(groups), "groups": groups})


@tool
async def get_group_stats(group_id: int, config: RunnableConfig = None) -> str:
    """Get statistics for a group: document count, storage bytes, member count, owner. Admin only."""
    if not _admin_info(config):
        return _deny()
    from app.dependencies import async_session_factory
    from app.group.models import Group, GroupMembership
    from app.document.models import Document
    from sqlalchemy import select, func

    async with async_session_factory() as s:
        g = (await s.execute(select(Group).where(Group.id == group_id))).scalar_one_or_none()
        if g is None or g.status == "DELETED":
            return json.dumps({"ok": False, "message": f"群组 {group_id} 不存在"}, ensure_ascii=False)
        mc = (await s.execute(
            select(func.count()).select_from(GroupMembership).where(GroupMembership.group_id == group_id)
        )).scalar() or 0
        row = (await s.execute(
            select(func.count(), func.coalesce(func.sum(Document.file_size), 0))
            .where(Document.group_id == group_id, Document.deleted == False)  # noqa: E712
        )).one()
        return _ok({
            "groupId": g.id, "groupCode": g.group_code, "groupName": g.group_name,
            "status": g.status, "ownerUserId": g.owner_user_id,
            "memberCount": mc, "documentCount": row[0], "storageBytes": int(row[1] or 0),
        })


@tool
async def list_group_members(group_id: int, config: RunnableConfig = None) -> str:
    """List members of a group with their roles. Admin only."""
    if not _admin_info(config):
        return _deny()
    from app.dependencies import async_session_factory
    from app.group.models import GroupMembership
    from app.auth.models import User
    from sqlalchemy import select

    async with async_session_factory() as s:
        rows = (await s.execute(
            select(User.id, User.user_code, User.display_name, User.email, GroupMembership.role)
            .join(GroupMembership, GroupMembership.user_id == User.id)
            .where(GroupMembership.group_id == group_id)
            .order_by(GroupMembership.role, User.id)
        )).all()
        members = [{
            "userId": uid, "userCode": ucode, "displayName": dname,
            "email": email, "role": role,
        } for uid, ucode, dname, email, role in rows]
    return _ok({"groupId": group_id, "count": len(members), "members": members})


@tool
async def list_documents(group_id: Optional[int] = None, status: Optional[str] = None,
                         keyword: Optional[str] = None, config: RunnableConfig = None) -> str:
    """List documents platform-wide. Filters: group_id, status (READY/PROCESSING/FAILED/UPLOADED), keyword (file name contains). Admin only."""
    if not _admin_info(config):
        return _deny()
    from app.dependencies import async_session_factory
    from app.document.models import Document
    from app.group.models import Group
    from app.auth.models import User
    from sqlalchemy import select

    stmt = (
        select(Document, Group.group_name, User.display_name)
        .join(Group, Document.group_id == Group.id)
        .join(User, Document.uploader_user_id == User.id)
        .where(Document.deleted == False)  # noqa: E712
    )
    if group_id is not None:
        stmt = stmt.where(Document.group_id == group_id)
    if status:
        stmt = stmt.where(Document.status == status.upper())
    if keyword:
        stmt = stmt.where(Document.file_name.ilike(f"%{keyword}%"))
    stmt = stmt.order_by(Document.id.desc()).limit(20)

    async with async_session_factory() as s:
        rows = (await s.execute(stmt)).all()
        docs = [{
            "documentId": d.id, "fileName": d.file_name, "fileExt": d.file_ext,
            "fileSize": d.file_size, "status": d.status,
            "groupId": d.group_id, "groupName": gn or "",
            "uploader": un or d.uploader_user_id, "uploadedAt": str(d.uploaded_at or ""),
        } for d, gn, un in rows]
    return _ok({"count": len(docs), "documents": docs})


@tool
async def search_knowledge(query: str, group_id: Optional[int] = None,
                           config: RunnableConfig = None) -> str:
    """Search knowledge base content (chunks) across groups, or within one group if group_id given. Returns evidence snippets with source files. Admin only."""
    if not _admin_info(config):
        return _deny()
    from app.dependencies import async_session_factory
    from app.group.models import Group
    from sqlalchemy import select

    vector_adapter = PgVectorRetrievalAdapter(settings.database_url)
    retrieval = HybridChunkRetrievalService(vector_adapter)

    async with async_session_factory() as s:
        if group_id is not None:
            group_ids = [group_id]
        else:
            group_ids = list((await s.execute(
                select(Group.id).where(Group.status == "ACTIVE")
            )).scalars().all())

    all_docs = []
    for gid in group_ids[:10]:
        try:
            bundle = await retrieval.retrieve(gid, query, [query])
            for doc in bundle.documents:
                all_docs.append({
                    "groupId": gid, "file": doc.source_file,
                    "evidenceLevel": bundle.evidence_level.value,
                    "snippet": doc.content[:300],
                })
        except Exception as e:
            logger.warning("search_knowledge group %s failed: %s", gid, e)
    return _ok({"count": len(all_docs), "results": all_docs})


@tool
async def ban_group(group_id: int, config: RunnableConfig = None) -> str:
    """Disable a group (members lose access). Requires user confirmation via interrupt. Admin only."""
    admin = _admin_info(config)
    if not admin:
        return _deny()
    from app.dependencies import async_session_factory
    from app.group.models import Group
    from app.audit.service import AuditService
    from sqlalchemy import select, update

    async with async_session_factory() as s:
        g = (await s.execute(select(Group).where(Group.id == group_id, Group.status != "DELETED"))).scalar_one_or_none()
        if g is None:
            return json.dumps({"ok": False, "message": f"群组 {group_id} 不存在"}, ensure_ascii=False)
        name = g.group_name

    decision = await _confirm_interrupt("ban_group", f"群组「{name}」(ID {group_id})",
                                        "停用后该群组成员将无法访问群组及其文档")
    if decision != "confirm":
        return _ok({"message": "已取消停用操作", "cancelled": True})

    async with async_session_factory() as s:
        await s.execute(update(Group).where(Group.id == group_id).values(status="DISABLED"))
        await AuditService(s).log(admin["user_id"], admin["user_code"], "GROUP_BAN", "group", group_id,
                                  {"groupName": name})
        await s.commit()
    return _ok({"message": f"群组「{name}」已停用"})


@tool
async def unban_group(group_id: int, config: RunnableConfig = None) -> str:
    """Restore a disabled group to active. Requires user confirmation via interrupt. Admin only."""
    admin = _admin_info(config)
    if not admin:
        return _deny()
    from app.dependencies import async_session_factory
    from app.group.models import Group
    from app.audit.service import AuditService
    from sqlalchemy import select, update

    async with async_session_factory() as s:
        g = (await s.execute(select(Group).where(Group.id == group_id, Group.status == "DISABLED"))).scalar_one_or_none()
        if g is None:
            return json.dumps({"ok": False, "message": f"群组 {group_id} 不存在或未停用"}, ensure_ascii=False)
        name = g.group_name

    decision = await _confirm_interrupt("unban_group", f"群组「{name}」(ID {group_id})",
                                        "恢复后该群组成员可重新访问群组及文档")
    if decision != "confirm":
        return _ok({"message": "已取消恢复操作", "cancelled": True})

    async with async_session_factory() as s:
        await s.execute(update(Group).where(Group.id == group_id).values(status="ACTIVE"))
        await AuditService(s).log(admin["user_id"], admin["user_code"], "GROUP_UNBAN", "group", group_id,
                                  {"groupName": name})
        await s.commit()
    return _ok({"message": f"群组「{name}」已恢复"})


@tool
async def delete_document(document_id: int, config: RunnableConfig = None) -> str:
    """Delete a document permanently (soft delete + index cleanup). Requires user confirmation via interrupt. Admin only."""
    admin = _admin_info(config)
    if not admin:
        return _deny()
    from app.dependencies import async_session_factory
    from app.document.models import Document
    from app.document.service import DocumentQueryService
    from app.audit.service import AuditService
    from sqlalchemy import select

    async with async_session_factory() as s:
        d = (await s.execute(select(Document).where(Document.id == document_id))).scalar_one_or_none()
        if d is None or d.deleted:
            return json.dumps({"ok": False, "message": f"文档 {document_id} 不存在"}, ensure_ascii=False)
        fname = d.file_name

    decision = await _confirm_interrupt("delete_document", f"文档「{fname}」(ID {document_id})",
                                        "删除后文档将被移除并清理检索索引，不可恢复")
    if decision != "confirm":
        return _ok({"message": "已取消删除操作", "cancelled": True})

    async with async_session_factory() as s:
        service = DocumentQueryService(s)
        cleanup = await service.delete(admin["user_id"], document_id)
        await AuditService(s).log(admin["user_id"], admin["user_code"], "DOCUMENT_DELETE", "document",
                                  document_id, {"fileName": fname})
        await s.commit()
    ok_all = all(cleanup.values())
    return _ok({"message": f"文档「{fname}」已删除",
                "cleanupOk": ok_all,
                "warning": "" if ok_all else "部分索引清理失败（向量/搜索/存储），可能有残留"})


@tool
async def list_users(config: RunnableConfig = None) -> str:
    """List platform users with role, status, activity (QA count) and LLM usage (calls/tokens/cost). Admin only."""
    if not _admin_info(config):
        return _deny()
    from app.dependencies import async_session_factory
    from app.auth.models import User
    from app.qa.models import QaSession
    from app.metrics.models import LlmUsageRecord
    from sqlalchemy import select, func

    async with async_session_factory() as s:
        users = (await s.execute(
            select(User).order_by(User.created_at.desc()).limit(50)
        )).scalars().all()
        qa_map = {uid: cnt for uid, cnt in (await s.execute(
            select(QaSession.user_id, func.count()).group_by(QaSession.user_id)
        )).all()}
        usage_rows = (await s.execute(
            select(LlmUsageRecord.user_id,
                   func.count(), func.sum(LlmUsageRecord.total_tokens),
                   func.sum(LlmUsageRecord.cost_amount))
            .group_by(LlmUsageRecord.user_id)
        )).all()
        # 费用按新计价口径 ×10（与前端展示一致）
        usage_map = {uid: {"calls": c or 0, "tokens": t or 0, "cost": float(cost or 0) * 10}
                     for uid, c, t, cost in usage_rows}
        items = [{
            "userId": u.id, "userCode": u.user_code, "username": u.username,
            "email": u.email, "displayName": u.display_name,
            "systemRole": u.system_role, "status": u.status,
            "mustChangePassword": u.must_change_password,
            "lastLoginAt": str(u.last_login_at or ""),
            "qaCount": qa_map.get(u.id, 0),
            "llmCalls": usage_map.get(u.id, {}).get("calls", 0),
            "llmTokens": usage_map.get(u.id, {}).get("tokens", 0),
            "llmCost": usage_map.get(u.id, {}).get("cost", 0.0),
        } for u in users]
    return _ok({"count": len(items), "users": items})


@tool
async def update_user_status(user_id: int, status: str, config: RunnableConfig = None) -> str:
    """Enable or disable a user account. status: ACTIVE or DISABLED. Requires user confirmation via interrupt. Admin only."""
    admin = _admin_info(config)
    if not admin:
        return _deny()
    from app.dependencies import async_session_factory
    from app.auth.models import User
    from app.audit.service import AuditService
    from sqlalchemy import select, update

    async with async_session_factory() as s:
        u = (await s.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if u is None:
            return json.dumps({"ok": False, "message": f"用户 {user_id} 不存在"}, ensure_ascii=False)
        name = u.display_name or u.username
        current = u.status
    if status not in ("ACTIVE", "DISABLED"):
        return json.dumps({"ok": False, "message": "状态必须是 ACTIVE 或 DISABLED"}, ensure_ascii=False)
    if status == current:
        return _ok({"message": f"用户「{name}」当前已是 {current}，无需变更"})

    action_label = "禁用" if status == "DISABLED" else "启用"
    decision = await _confirm_interrupt("update_user_status", f"用户「{name}」(ID {user_id})",
                                        f"{action_label}后该用户{'将无法登录系统' if status == 'DISABLED' else '可恢复正常登录'}")
    if decision != "confirm":
        return _ok({"message": f"已取消{action_label}操作", "cancelled": True})

    async with async_session_factory() as s:
        await s.execute(update(User).where(User.id == user_id).values(status=status))
        await AuditService(s).log(admin["user_id"], admin["user_code"], "USER_STATUS_CHANGE",
                                  "user", user_id, {"status": status})
        await s.commit()
    return _ok({"message": f"用户「{name}」已{action_label}"})


@tool
async def list_audit_logs(action: Optional[str] = None, user_id: Optional[int] = None,
                          limit: int = 20, config: RunnableConfig = None) -> str:
    """List audit logs (sensitive operations): document delete/retry, group ban/unban/dissolve, user create/disable, model config changes. Filters: action (DOCUMENT_DELETE/GROUP_BAN/USER_STATUS_CHANGE...), user_id. Admin only."""
    if not _admin_info(config):
        return _deny()
    from app.dependencies import async_session_factory
    from app.audit.models import AuditLog
    from sqlalchemy import select

    stmt = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(min(limit, 50))
    if action:
        stmt = stmt.where(AuditLog.action == action.upper())
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)

    async with async_session_factory() as s:
        rows = (await s.execute(stmt)).scalars().all()
        items = [{
            "id": log.id, "username": log.username, "action": log.action,
            "targetType": log.target_type, "targetId": log.target_id,
            "detail": log.detail or {}, "createdAt": str(log.created_at or ""),
        } for log in rows]
    return _ok({"count": len(items), "logs": items})


@tool
async def generate_report(topic: str, period: Optional[str] = None,
                          config: RunnableConfig = None) -> str:
    """Generate a detailed platform report on the given topic. Collects platform-wide snapshot data (users, groups, documents, QA, LLM usage, audit summary); the assistant then composes a readable report. topic examples: 用户用量报告 / 群组活跃报告 / 平台运行报告. period: TODAY/LAST_7_DAYS/LAST_30_DAYS (default all-time). Admin only."""
    if not _admin_info(config):
        return _deny()
    from datetime import timedelta
    from app.common.time_utils import utcnow
    from app.dependencies import async_session_factory
    from app.auth.models import User
    from app.group.models import Group
    from app.document.models import Document
    from app.ingestion.models import DocumentChunk
    from app.qa.models import QaSession, QaMessage
    from app.metrics.models import LlmUsageRecord
    from app.audit.models import AuditLog
    from sqlalchemy import select, func

    since = None
    if period == "TODAY":
        since = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "LAST_7_DAYS":
        since = utcnow() - timedelta(days=7)
    elif period == "LAST_30_DAYS":
        since = utcnow() - timedelta(days=30)

    async with async_session_factory() as s:
        total_users = (await s.execute(select(func.count()).select_from(User))).scalar() or 0
        total_groups = (await s.execute(select(func.count()).select_from(Group))).scalar() or 0
        doc_stats = (await s.execute(
            select(Document.status, func.count()).where(Document.deleted == False)  # noqa: E712
            .group_by(Document.status)
        )).all()
        total_chunks = (await s.execute(select(func.count()).select_from(DocumentChunk))).scalar() or 0
        storage = (await s.execute(
            select(func.coalesce(func.sum(Document.file_size), 0))
            .where(Document.deleted == False)  # noqa: E712
        )).scalar() or 0

        qa_stmt = select(func.count()).select_from(QaSession)
        refused_stmt = select(func.count()).select_from(QaMessage).where(
            QaMessage.role == "ASSISTANT", QaMessage.reason_code == "NO_EVIDENCE")
        if since:
            qa_stmt = qa_stmt.where(QaSession.created_at >= since)
            refused_stmt = refused_stmt.where(QaMessage.created_at >= since)
        total_qa = (await s.execute(qa_stmt)).scalar() or 0
        refused_qa = (await s.execute(refused_stmt)).scalar() or 0

        # 用户用量 TOP 5
        user_stmt = (
            select(User.display_name, func.count(), func.sum(LlmUsageRecord.total_tokens),
                   func.sum(LlmUsageRecord.cost_amount))
            .join(LlmUsageRecord, LlmUsageRecord.user_id == User.id)
        )
        if since:
            user_stmt = user_stmt.where(LlmUsageRecord.created_at >= since)
        user_rows = (await s.execute(
            user_stmt.group_by(User.id, User.display_name)
            .order_by(func.sum(LlmUsageRecord.total_tokens).desc()).limit(5)
        )).all()
        top_users = [{"name": n, "calls": c or 0, "tokens": int(t or 0), "cost": float(cost or 0) * 10}
                     for n, c, t, cost in user_rows]

        # 群组文档 TOP 5
        group_rows = (await s.execute(
            select(Group.group_name, func.count(), func.coalesce(func.sum(Document.file_size), 0))
            .join(Document, Document.group_id == Group.id)
            .where(Document.deleted == False)  # noqa: E712
            .group_by(Group.id, Group.group_name)
            .order_by(func.count().desc()).limit(5)
        )).all()
        top_groups = [{"name": n, "documents": c, "storageBytes": int(st or 0)}
                      for n, c, st in group_rows]

        # 审计摘要（最近操作）
        audit_rows = (await s.execute(
            select(AuditLog.action, func.count())
            .group_by(AuditLog.action).order_by(func.count().desc()).limit(8)
        )).all()
        audit_summary = {a: c for a, c in audit_rows}

    return _ok({
        "topic": topic, "period": period or "全部时间",
        "overview": {
            "users": total_users, "groups": total_groups,
            "documents": {st: cnt for st, cnt in doc_stats},
            "chunks": total_chunks, "storageBytes": int(storage),
            "qaSessions": total_qa, "refusedQa": refused_qa,
        },
        "topUsers": top_users,
        "topGroups": top_groups,
        "auditSummary": audit_summary,
    })


ADMIN_TOOLS = [
    list_groups, get_group_stats, list_group_members,
    list_documents, search_knowledge,
    ban_group, unban_group, delete_document,
    list_users, update_user_status, list_audit_logs, generate_report,
]
