from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class CreateGroupRequest(BaseModel):
    group_name: str = Field(..., min_length=1, max_length=128, alias="groupName")
    description: str = Field(default="", max_length=2000)

    model_config = {"populate_by_name": True}


class UpdateGroupRequest(BaseModel):
    group_name: str = Field(..., min_length=1, max_length=128, alias="groupName")
    description: str = Field(default="", max_length=2000)

    model_config = {"populate_by_name": True}


class GroupResponse(BaseModel):
    id: int
    group_code: str
    group_name: str
    description: str
    owner_user_id: int
    status: str
    my_role: Optional[str] = None
    created_at: Optional[str] = None


class GroupMemberResponse(BaseModel):
    id: int
    user_id: int
    username: str
    display_name: str
    email: str
    role: str
    joined_at: Optional[str] = None


class CreateInvitationRequest(BaseModel):
    invitee_user_id: int = Field(..., alias="inviteeUserId")

    model_config = {"populate_by_name": True}


class CreateJoinRequestRequest(BaseModel):
    pass  # No body needed; groupId in path


class MySentInvitationResponse(BaseModel):
    id: int
    group_id: int
    group_name: str
    invitee_user_id: int
    invitee_username: str
    invitee_display_name: str
    status: str
    created_at: Optional[str] = None


class MyJoinRequestResponse(BaseModel):
    id: int
    group_id: int
    group_name: str
    status: str
    created_at: Optional[str] = None


class OwnerJoinRequestResponse(BaseModel):
    id: int
    group_id: int
    group_name: str
    applicant_user_id: int
    applicant_username: str
    applicant_display_name: str
    status: str
    created_at: Optional[str] = None
