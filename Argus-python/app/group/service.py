import uuid
import logging
from datetime import datetime

from app.common.time_utils import utcnow
from typing import Optional, List

from sqlalchemy import select, update, delete, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.group.models import Group, GroupMembership, GroupInvitation, GroupJoinRequest
from app.common.exception.exceptions import BusinessException, ForbiddenException

logger = logging.getLogger(__name__)

GROUP_ROLE_OWNER = "OWNER"
GROUP_ROLE_MEMBER = "MEMBER"
GROUP_STATUS_ACTIVE = "ACTIVE"
INVITE_STATUS_PENDING = "PENDING"
INVITE_STATUS_ACCEPTED = "ACCEPTED"
INVITE_STATUS_REFUSED = "REFUSED"
INVITE_STATUS_CANCELLED = "CANCELLED"
REQUEST_STATUS_PENDING = "PENDING"
REQUEST_STATUS_APPROVED = "APPROVED"
REQUEST_STATUS_REJECTED = "REJECTED"
REQUEST_STATUS_CANCELLED = "CANCELLED"


def _fmt(dt) -> Optional[str]:
    # UTC suffix so browsers parse it as UTC (consistent with other modules)
    return dt.isoformat() + "Z" if dt else None


async def require_group_access(
    session: AsyncSession,
    user_id: int,
    system_role: str,
    group_id: int,
) -> None:
    """系统管理员或群组成员可访问，否则抛出 ForbiddenException。"""
    if system_role == "ADMIN":
        return
    group_status = (await session.execute(
        select(Group.status).where(Group.id == group_id)
    )).scalar_one_or_none()
    if group_status != "ACTIVE":
        raise ForbiddenException("群组已被停用或解散")
    result = await session.execute(
        select(GroupMembership).where(
            GroupMembership.group_id == group_id,
            GroupMembership.user_id == user_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise ForbiddenException("无权访问该群组")


class GroupManagementService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_my_groups(self, user_id: int) -> dict:
        result = await self.session.execute(
            select(GroupMembership).where(GroupMembership.user_id == user_id)
        )
        memberships = result.scalars().all()
        if not memberships:
            return {"owned_groups": [], "joined_groups": [], "pending_invitations": []}

        group_ids = [m.group_id for m in memberships]
        role_map = {m.group_id: m.role for m in memberships}

        result = await self.session.execute(
            select(Group).where(Group.id.in_(group_ids)).order_by(Group.created_at.desc())
        )
        all_groups = [
            {
                "group_id": g.id, "group_code": g.group_code,
                "group_name": g.group_name, "description": g.description or "",
                "created_at": _fmt(g.created_at),
            }
            for g in result.scalars()
        ]

        owned_groups = [g for g in all_groups if role_map.get(g["group_id"]) == GROUP_ROLE_OWNER]
        joined_groups = [g for g in all_groups if role_map.get(g["group_id"]) == GROUP_ROLE_MEMBER]

        # Add pending join request counts for owned groups
        if owned_groups:
            owned_ids = [g["group_id"] for g in owned_groups]
            req_counts = await self.session.execute(
                select(
                    GroupJoinRequest.group_id,
                    func.count().label("cnt"),
                )
                .where(
                    GroupJoinRequest.group_id.in_(owned_ids),
                    GroupJoinRequest.status == REQUEST_STATUS_PENDING,
                )
                .group_by(GroupJoinRequest.group_id)
            )
            count_map = {row.group_id: row.cnt for row in req_counts}
            for g in owned_groups:
                g["pending_request_count"] = count_map.get(g["group_id"], 0)

        # Pending invitations
        inv_result = await self.session.execute(
            select(GroupInvitation, Group, User)
            .join(Group, GroupInvitation.group_id == Group.id)
            .join(User, GroupInvitation.inviter_user_id == User.id)
            .where(
                GroupInvitation.invitee_user_id == user_id,
                GroupInvitation.status == INVITE_STATUS_PENDING,
            )
            .order_by(GroupInvitation.created_at.desc())
        )
        pending_invitations = [
            {
                "invitation_id": inv.id, "group_id": g.id,
                "group_name": g.group_name,
                "inviter_user_id": inv.inviter_user_id,
                "inviter_display_name": u.display_name,
                "status": inv.status,
            }
            for inv, g, u in inv_result
        ]

        return {
            "owned_groups": owned_groups,
            "joined_groups": joined_groups,
            "pending_invitations": pending_invitations,
        }

    async def create_group(self, user_id: int, group_name: str, description: str) -> dict:
        group_code = uuid.uuid4().hex[:12]

        group = Group(
            group_code=group_code,
            group_name=group_name.strip(),
            description=description.strip(),
            owner_user_id=user_id,
            status=GROUP_STATUS_ACTIVE,
        )
        self.session.add(group)
        await self.session.flush()

        membership = GroupMembership(
            group_id=group.id,
            user_id=user_id,
            role=GROUP_ROLE_OWNER,
        )
        self.session.add(membership)
        await self.session.flush()

        logger.info("Group created: id=%s, owner=%s", group.id, user_id)
        return {
            "id": group.id, "group_code": group.group_code,
            "group_name": group.group_name, "description": group.description,
            "owner_user_id": group.owner_user_id, "status": group.status,
            "my_role": GROUP_ROLE_OWNER, "created_at": _fmt(group.created_at),
        }

    async def update_group(self, user_id: int, group_id: int, group_name: str, description: str) -> dict:
        await self._require_owner(user_id, group_id)

        await self.session.execute(
            update(Group)
            .where(Group.id == group_id)
            .values(group_name=group_name.strip(), description=description.strip(),
                    updated_at=utcnow())
        )
        await self.session.flush()

        result = await self.session.execute(select(Group).where(Group.id == group_id))
        g = result.scalar_one()
        return {
            "id": g.id, "group_code": g.group_code, "group_name": g.group_name,
            "description": g.description, "owner_user_id": g.owner_user_id,
            "status": g.status, "created_at": _fmt(g.created_at),
        }

    async def delete_group(self, user_id: int, group_id: int) -> None:
        await self._require_owner(user_id, group_id)

        await self.session.execute(delete(GroupMembership).where(GroupMembership.group_id == group_id))
        await self.session.execute(delete(GroupJoinRequest).where(GroupJoinRequest.group_id == group_id))
        await self.session.execute(delete(GroupInvitation).where(GroupInvitation.group_id == group_id))
        await self.session.execute(delete(Group).where(Group.id == group_id))
        logger.info("Group deleted: id=%s, by=%s", group_id, user_id)

    async def _require_owner(self, user_id: int, group_id: int) -> Group:
        result = await self.session.execute(select(Group).where(Group.id == group_id))
        group = result.scalar_one_or_none()
        if group is None:
            raise BusinessException("群组不存在")
        if group.owner_user_id != user_id:
            raise ForbiddenException("只有群组所有者可以执行此操作")
        return group


class GroupMembershipService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_members(self, group_id: int) -> List[dict]:
        result = await self.session.execute(
            select(GroupMembership, User)
            .join(User, GroupMembership.user_id == User.id)
            .where(GroupMembership.group_id == group_id)
            .order_by(GroupMembership.created_at)
        )
        return [
            {
                "id": m.id, "user_id": m.user_id, "username": u.username,
                "display_name": u.display_name, "email": u.email,
                "role": m.role, "joined_at": _fmt(m.created_at),
            }
            for m, u in result
        ]

    async def leave_group(self, user_id: int, group_id: int) -> None:
        result = await self.session.execute(select(Group).where(Group.id == group_id))
        group = result.scalar_one_or_none()
        if group is None:
            raise BusinessException("群组不存在")
        if group.owner_user_id == user_id:
            raise BusinessException("OWNER 不能退出自己的组")

        result = await self.session.execute(
            select(GroupMembership).where(
                GroupMembership.group_id == group_id,
                GroupMembership.user_id == user_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise BusinessException("当前用户不是目标群组成员")

        await self.session.execute(
            delete(GroupMembership).where(
                GroupMembership.group_id == group_id,
                GroupMembership.user_id == user_id,
            )
        )
        logger.info("User %s left group %s", user_id, group_id)

    async def remove_member(self, operator_id: int, group_id: int, user_id: int) -> None:
        result = await self.session.execute(select(Group).where(Group.id == group_id))
        group = result.scalar_one_or_none()
        if group is None:
            raise BusinessException("群组不存在")
        if group.owner_user_id != operator_id:
            raise ForbiddenException("只有群组所有者可以移除成员")
        if user_id == group.owner_user_id:
            raise BusinessException("不能移除群组所有者")

        await self.session.execute(
            delete(GroupMembership).where(
                GroupMembership.group_id == group_id,
                GroupMembership.user_id == user_id,
            )
        )


class GroupJoinRequestService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def submit_request(self, user_id: int, group_id: int) -> dict:
        result = await self.session.execute(
            select(GroupMembership).where(
                GroupMembership.group_id == group_id,
                GroupMembership.user_id == user_id,
            )
        )
        if result.scalar_one_or_none():
            raise BusinessException("你已经是该群组成员")

        result = await self.session.execute(
            select(GroupJoinRequest).where(
                GroupJoinRequest.group_id == group_id,
                GroupJoinRequest.applicant_user_id == user_id,
                GroupJoinRequest.status == REQUEST_STATUS_PENDING,
            )
        )
        if result.scalar_one_or_none():
            raise BusinessException("你已提交过加入申请，请等待审批")

        req = GroupJoinRequest(
            group_id=group_id,
            applicant_user_id=user_id,
            status=REQUEST_STATUS_PENDING,
        )
        self.session.add(req)
        await self.session.flush()

        return {"id": req.id, "group_id": req.group_id, "status": req.status,
                "created_at": _fmt(req.created_at)}

    async def submit_request_by_code(self, user_id: int, group_code: str) -> dict:
        result = await self.session.execute(
            select(Group).where(Group.group_code == group_code)
        )
        group = result.scalar_one_or_none()
        if group is None:
            raise BusinessException("组织 ID 不存在")
        return await self.submit_request(user_id, group.id)

    async def list_my_requests(self, user_id: int) -> List[dict]:
        result = await self.session.execute(
            select(GroupJoinRequest, Group.group_name)
            .join(Group, GroupJoinRequest.group_id == Group.id)
            .where(GroupJoinRequest.applicant_user_id == user_id)
            .order_by(GroupJoinRequest.created_at.desc())
        )
        return [
            {"request_id": r.id, "group_id": r.group_id, "group_name": name,
             "status": r.status, "created_at": _fmt(r.created_at),
             "decided_at": _fmt(r.decided_at)}
            for r, name in result
        ]

    async def list_pending_for_owner(self, owner_id: int, group_id: int) -> List[dict]:
        result = await self.session.execute(select(Group).where(Group.id == group_id))
        group = result.scalar_one_or_none()
        if group is None:
            raise BusinessException("群组不存在")
        if group.owner_user_id != owner_id:
            raise ForbiddenException("只有群组所有者可以查看申请")

        result = await self.session.execute(
            select(GroupJoinRequest, User.username, User.display_name)
            .join(User, GroupJoinRequest.applicant_user_id == User.id)
            .where(
                GroupJoinRequest.group_id == group_id,
                GroupJoinRequest.status == REQUEST_STATUS_PENDING,
            )
            .order_by(GroupJoinRequest.created_at)
        )
        return [
            {"request_id": r.id, "group_id": r.group_id, "group_name": group.group_name,
             "applicant_user_id": r.applicant_user_id,
             "applicant_username": uname, "applicant_display_name": dname,
             "status": r.status, "created_at": _fmt(r.created_at)}
            for r, uname, dname in result
        ]

    async def process_request(self, owner_id: int, request_id: int, approved: bool) -> None:
        result = await self.session.execute(
            select(GroupJoinRequest, Group)
            .join(Group, GroupJoinRequest.group_id == Group.id)
            .where(GroupJoinRequest.id == request_id)
        )
        row = result.one_or_none()
        if row is None:
            raise BusinessException("申请不存在")
        req, group = row
        if group.owner_user_id != owner_id:
            raise ForbiddenException("只有群组所有者可以审批申请")
        if req.status != REQUEST_STATUS_PENDING:
            raise BusinessException("该申请已被处理")

        now = utcnow()
        new_status = REQUEST_STATUS_APPROVED if approved else REQUEST_STATUS_REJECTED
        req.status = new_status
        req.decided_by_user_id = owner_id
        req.decided_at = now

        if approved:
            existing = await self.session.execute(
                select(GroupMembership).where(
                    GroupMembership.group_id == req.group_id,
                    GroupMembership.user_id == req.applicant_user_id,
                )
            )
            if not existing.scalar_one_or_none():
                self.session.add(GroupMembership(
                    group_id=req.group_id,
                    user_id=req.applicant_user_id,
                    role=GROUP_ROLE_MEMBER,
                ))

        await self.session.flush()


class GroupInvitationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_invitation(self, inviter_id: int, group_id: int, invitee_user_id: int) -> dict:
        result = await self.session.execute(select(Group).where(Group.id == group_id))
        group = result.scalar_one_or_none()
        if group is None:
            raise BusinessException("群组不存在")
        if group.owner_user_id != inviter_id:
            raise ForbiddenException("只有群组所有者可以邀请")

        result = await self.session.execute(
            select(GroupMembership).where(
                GroupMembership.group_id == group_id,
                GroupMembership.user_id == invitee_user_id,
            )
        )
        if result.scalar_one_or_none():
            raise BusinessException("该用户已是群组成员")

        result = await self.session.execute(
            select(GroupInvitation).where(
                GroupInvitation.group_id == group_id,
                GroupInvitation.invitee_user_id == invitee_user_id,
                GroupInvitation.status == INVITE_STATUS_PENDING,
            )
        )
        if result.scalar_one_or_none():
            raise BusinessException("已发送过邀请，请等待对方处理")

        inv = GroupInvitation(
            group_id=group_id,
            inviter_user_id=inviter_id,
            invitee_user_id=invitee_user_id,
            status=INVITE_STATUS_PENDING,
        )
        self.session.add(inv)
        await self.session.flush()
        return {"id": inv.id, "group_id": inv.group_id, "group_name": group.group_name,
                "invitee_user_id": inv.invitee_user_id, "status": inv.status,
                "created_at": _fmt(inv.created_at)}

    async def list_my_invitations(self, user_id: int) -> List[dict]:
        result = await self.session.execute(
            select(GroupInvitation, Group.group_name)
            .join(Group, GroupInvitation.group_id == Group.id)
            .where(GroupInvitation.invitee_user_id == user_id)
            .order_by(GroupInvitation.created_at.desc())
        )
        return [
            {"invitation_id": inv.id, "group_id": inv.group_id, "group_name": name,
             "inviter_user_id": inv.inviter_user_id,
             "status": inv.status, "created_at": _fmt(inv.created_at),
             "decided_at": _fmt(inv.decided_at)}
            for inv, name in result
        ]

    async def list_my_sent_invitations(self, user_id: int) -> List[dict]:
        result = await self.session.execute(
            select(GroupInvitation, Group.group_name, User.username, User.display_name)
            .join(Group, GroupInvitation.group_id == Group.id)
            .join(User, GroupInvitation.invitee_user_id == User.id)
            .where(GroupInvitation.inviter_user_id == user_id)
            .order_by(GroupInvitation.created_at.desc())
        )
        return [
            {"invitation_id": inv.id, "group_id": inv.group_id, "group_name": gname,
             "invitee_user_id": inv.invitee_user_id,
             "invitee_username": uname, "invitee_display_name": dname,
             "status": inv.status, "created_at": _fmt(inv.created_at),
             "decided_at": _fmt(inv.decided_at)}
            for inv, gname, uname, dname in result
        ]

    async def respond_invitation(self, user_id: int, invitation_id: int, accepted: bool) -> None:
        result = await self.session.execute(
            select(GroupInvitation).where(GroupInvitation.id == invitation_id)
        )
        inv = result.scalar_one_or_none()
        if inv is None:
            raise BusinessException("邀请不存在")
        if inv.invitee_user_id != user_id:
            raise ForbiddenException("这不是发给你的邀请")
        if inv.status != INVITE_STATUS_PENDING:
            raise BusinessException("邀请已被处理")

        now = utcnow()
        inv.status = INVITE_STATUS_ACCEPTED if accepted else INVITE_STATUS_REFUSED
        inv.decided_at = now

        if accepted:
            existing = await self.session.execute(
                select(GroupMembership).where(
                    GroupMembership.group_id == inv.group_id,
                    GroupMembership.user_id == user_id,
                )
            )
            if not existing.scalar_one_or_none():
                self.session.add(GroupMembership(
                    group_id=inv.group_id,
                    user_id=user_id,
                    role=GROUP_ROLE_MEMBER,
                ))

        await self.session.flush()

    async def cancel_invitation(self, user_id: int, invitation_id: int) -> None:
        result = await self.session.execute(
            select(GroupInvitation, Group)
            .join(Group, GroupInvitation.group_id == Group.id)
            .where(GroupInvitation.id == invitation_id)
        )
        row = result.one_or_none()
        if row is None:
            raise BusinessException("邀请不存在")
        inv, group = row
        if group.owner_user_id != user_id:
            raise ForbiddenException("只有群组所有者可以取消邀请")
        if inv.status != INVITE_STATUS_PENDING:
            raise BusinessException("邀请已被处理")

        inv.status = INVITE_STATUS_CANCELLED
        inv.decided_at = utcnow()
        await self.session.flush()
