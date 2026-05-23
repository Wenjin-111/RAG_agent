from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
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
