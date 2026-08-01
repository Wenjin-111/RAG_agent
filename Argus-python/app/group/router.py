from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_audit
from app.auth.dependencies import get_current_user, require_admin
from app.common.response import ApiResponse
from app.common.security.context import AuthenticatedUser
from app.dependencies import get_db
from app.group.schemas import CreateInvitationRequest
from app.group.service import (
    GroupManagementService,
    GroupMembershipService,
    GroupJoinRequestService,
    GroupInvitationService,
)

router = APIRouter()

# ---- Group Query ----

@router.get("/my")
async def list_my_groups(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = GroupManagementService(db)
    groups = await service.list_my_groups(current_user.user_id)
    return ApiResponse.ok(data=groups)


# ---- Group CRUD ----

@router.post("")
async def create_group(
    body: dict,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = GroupManagementService(db)
    result = await service.create_group(current_user.user_id, body.get("name", ""), body.get("description", ""))
    return ApiResponse.ok(data=result["id"])


# ---- Members ----

@router.get("/{group_id}/members")
async def list_members(
    group_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = GroupMembershipService(db)
    members = await service.list_members(group_id)
    return ApiResponse.ok(data=members)


@router.delete("/{group_id}/members/{user_id}")
async def remove_member(
    group_id: int,
    user_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = GroupMembershipService(db)
    await service.remove_member(current_user.user_id, group_id, user_id)
    return ApiResponse.ok(message="成员已移除")


@router.post("/{group_id}/leave")
async def leave_group(
    group_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = GroupMembershipService(db)
    await service.leave_group(current_user.user_id, group_id)
    return ApiResponse.ok(message="已退出群组")


# ---- Admin: all groups (requires admin) ----
admin_router = APIRouter()


@admin_router.get("/groups")
async def admin_list_groups(
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select, func
    from app.group.models import Group, GroupMembership

    result = await db.execute(
        select(Group, func.count(GroupMembership.id).label("member_count"))
        .outerjoin(GroupMembership, GroupMembership.group_id == Group.id)
        .where(Group.status != "DELETED")
        .group_by(Group.id)
        .order_by(Group.created_at.desc())
    )
    items = []
    for g, member_count in result:
        items.append({
            "groupId": g.id,
            "groupCode": g.group_code,
            "groupName": g.group_name,
            "description": g.description or "",
            "ownerUserId": g.owner_user_id,
            "status": g.status,
            "memberCount": member_count,
            "createdAt": g.created_at.isoformat() + "Z" if g.created_at else None,
        })
    return ApiResponse.ok(data=items)


@admin_router.get("/groups/{group_id}")
async def admin_group_detail(
    group_id: int,
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select, func
    from app.group.models import Group
    from app.group.service import GroupMembershipService
    from app.document.models import Document

    result = await db.execute(select(Group).where(Group.id == group_id, Group.status != "DELETED"))
    group = result.scalar_one_or_none()
    if group is None:
        raise BusinessException("群组不存在")

    doc_result = await db.execute(
        select(func.count().label("doc_count"), func.sum(Document.file_size).label("storage_bytes"))
        .where(Document.group_id == group_id, Document.deleted == False)
    )
    dr = doc_result.one()

    members = await GroupMembershipService(db).list_members(group_id)
    return ApiResponse.ok(data={
        "groupId": group.id,
        "groupCode": group.group_code,
        "groupName": group.group_name,
        "description": group.description or "",
        "ownerUserId": group.owner_user_id,
        "status": group.status,
        "documentCount": dr.doc_count or 0,
        "storageBytes": dr.storage_bytes or 0,
        "memberCount": len(members),
        "members": members,
        "createdAt": group.created_at.isoformat() + "Z" if group.created_at else None,
    })


@admin_router.post("/groups/{group_id}/ban")
async def admin_ban_group(
    group_id: int,
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.group.models import Group
    from sqlalchemy import update

    result = await db.execute(select(Group).where(Group.id == group_id, Group.status != "DELETED"))
    group = result.scalar_one_or_none()
    if group is None:
        raise BusinessException("群组不存在")
    await db.execute(update(Group).where(Group.id == group_id).values(status="DISABLED"))
    await db.flush()
    await log_audit(db, _admin, "GROUP_BAN", "group", group_id, {"groupName": group.group_name})
    return ApiResponse.ok(message="群组已停用")


@admin_router.post("/groups/{group_id}/unban")
async def admin_unban_group(
    group_id: int,
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.group.models import Group
    from sqlalchemy import update

    result = await db.execute(select(Group).where(Group.id == group_id, Group.status != "DELETED"))
    group = result.scalar_one_or_none()
    if group is None:
        raise BusinessException("群组不存在")
    await db.execute(update(Group).where(Group.id == group_id).values(status="ACTIVE"))
    await db.flush()
    await log_audit(db, _admin, "GROUP_UNBAN", "group", group_id, {"groupName": group.group_name})
    return ApiResponse.ok(message="群组已恢复")


@admin_router.delete("/groups/{group_id}/members/{user_id}")
async def admin_remove_member(
    group_id: int,
    user_id: int,
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.group.models import Group, GroupMembership
    from sqlalchemy import delete

    result = await db.execute(select(Group).where(Group.id == group_id, Group.status != "DELETED"))
    group = result.scalar_one_or_none()
    if group is None:
        raise BusinessException("群组不存在")
    if user_id == group.owner_user_id:
        raise BusinessException("不能移除群组所有者")

    await db.execute(
        delete(GroupMembership).where(
            GroupMembership.group_id == group_id,
            GroupMembership.user_id == user_id,
        )
    )
    await db.flush()
    await log_audit(db, _admin, "GROUP_MEMBER_REMOVE", "group", group_id,
                    {"userId": user_id, "groupName": group.group_name})
    return ApiResponse.ok(message="成员已移除")


@admin_router.delete("/groups/{group_id}")
async def admin_dissolve_group(
    group_id: int,
    _admin: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """解散群组：软删群组与全部文档，清理切片/向量/搜索索引与成员关系。"""
    from sqlalchemy import delete, update
    from app.group.models import Group, GroupMembership, GroupInvitation, GroupJoinRequest
    from app.document.models import Document
    from app.ingestion.models import DocumentChunk

    result = await db.execute(select(Group).where(Group.id == group_id, Group.status != "DELETED"))
    group = result.scalar_one_or_none()
    if group is None:
        raise BusinessException("群组不存在")

    # 1. 软删群组
    await db.execute(update(Group).where(Group.id == group_id).values(status="DELETED"))
    await db.flush()

    # 2. 软删文档 + 收集 id
    doc_ids = (await db.execute(
        select(Document.id).where(Document.group_id == group_id, Document.deleted == False)
    )).scalars().all()
    if doc_ids:
        await db.execute(
            update(Document).where(Document.id.in_(doc_ids)).values(deleted=True)
        )
        await db.flush()
        # 3. 删切片
        await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id.in_(doc_ids)))
        await db.flush()
        # 4. 清向量 / ES（失败不阻塞解散）
        try:
            from app.engine.vector_store import PgVectorRetrievalAdapter
            from app.config import settings
            adapter = PgVectorRetrievalAdapter(settings.database_url)
            await adapter.delete_by_document_ids(list(doc_ids))
        except Exception:
            pass
        try:
            from app.engine.es_service import es_service
            await es_service.delete_by_document_ids(list(doc_ids))
        except Exception:
            pass

    # 5. 清成员关系 / 邀请 / 申请
    await db.execute(delete(GroupMembership).where(GroupMembership.group_id == group_id))
    await db.execute(delete(GroupInvitation).where(GroupInvitation.group_id == group_id))
    await db.execute(delete(GroupJoinRequest).where(GroupJoinRequest.group_id == group_id))
    await db.flush()
    await log_audit(db, _admin, "GROUP_DISSOLVE", "group", group_id,
                    {"groupName": group.group_name, "documentCount": len(doc_ids)})
    return ApiResponse.ok(message="群组已解散")


# ---- Invitations (at /api/invitations) ----
# Registered separately as a standalone router

invitation_router = APIRouter()


@invitation_router.post("/{invitation_id}/accept")
async def accept_invitation(
    invitation_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = GroupInvitationService(db)
    await service.respond_invitation(current_user.user_id, invitation_id, accepted=True)
    return ApiResponse.ok(message="已接受邀请")


@invitation_router.post("/{invitation_id}/reject")
async def refuse_invitation(
    invitation_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = GroupInvitationService(db)
    await service.respond_invitation(current_user.user_id, invitation_id, accepted=False)
    return ApiResponse.ok(message="已拒绝邀请")


@invitation_router.post("/{invitation_id}/cancel")
async def cancel_invitation(
    invitation_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = GroupInvitationService(db)
    await service.cancel_invitation(current_user.user_id, invitation_id)
    return ApiResponse.ok(message="已取消邀请")


# ---- Invitations (at /api/groups) ----

@router.post("/{group_id}/invitations")
async def create_invitation(
    group_id: int,
    body: dict,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = GroupInvitationService(db)
    result = await service.create_invitation(current_user.user_id, group_id, body.get("inviteeUserId", 0))
    return ApiResponse.ok(data=result["id"])


@router.get("/invitations/my-sent")
async def list_sent_invitations(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = GroupInvitationService(db)
    result = await service.list_my_sent_invitations(current_user.user_id)
    return ApiResponse.ok(data=result)


# ---- Join Requests ----

@router.post("/join-requests")
async def submit_join_request(
    body: dict,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = GroupJoinRequestService(db)
    result = await service.submit_request_by_code(current_user.user_id, body.get("groupCode", ""))
    return ApiResponse.ok(data=result["id"])


@router.get("/join-requests/my")
async def list_my_join_requests(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = GroupJoinRequestService(db)
    result = await service.list_my_requests(current_user.user_id)
    return ApiResponse.ok(data=result)


@router.get("/{group_id}/join-requests")
async def list_pending_join_requests(
    group_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = GroupJoinRequestService(db)
    result = await service.list_pending_for_owner(current_user.user_id, group_id)
    return ApiResponse.ok(data=result)


@router.post("/{group_id}/join-requests/{request_id}/approve")
async def approve_join_request(
    group_id: int,
    request_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = GroupJoinRequestService(db)
    await service.process_request(current_user.user_id, request_id, approved=True)
    return ApiResponse.ok(message="已批准申请")


@router.post("/{group_id}/join-requests/{request_id}/reject")
async def reject_join_request(
    group_id: int,
    request_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = GroupJoinRequestService(db)
    await service.process_request(current_user.user_id, request_id, approved=False)
    return ApiResponse.ok(message="已拒绝申请")
