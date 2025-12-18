from datetime import datetime, date
from typing import List, Optional
from pydantic import BaseModel, Field, EmailStr


# Enums
class ProjectStatus(str):
    ACTIVE = "active"
    ARCHIVED = "archived"
    COMPLETED = "completed"


class TaskStatus(str):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"


class TaskPriority(str):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


# Base models
class ProjectBase(BaseModel):
    name: str
    status: ProjectStatus


class UserBase(BaseModel):
    username: str
    email: EmailStr


class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[date] = Field(None, alias="dueDate")
    status: TaskStatus
    project_id: int = Field(..., alias="projectId")
    assignee_id: Optional[int] = Field(None, alias="assigneeId")


class TagBase(BaseModel):
    name: str
    color: Optional[str] = None


# Create models
class ProjectCreate(ProjectBase):
    pass


class UserCreate(UserBase):
    pass


class TaskCreate(TaskBase):
    pass


class TagCreate(TagBase):
    pass


# Update models
class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[ProjectStatus] = None


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[date] = Field(None, alias="dueDate")
    status: Optional[TaskStatus] = None
    project_id: Optional[int] = Field(None, alias="projectId")
    assignee_id: Optional[int] = Field(None, alias="assigneeId")


class TagUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None


# Response models
class ProjectResponse(BaseModel):
    id: int
    name: str
    status: ProjectStatus
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")

    model_config = {"populate_by_name": True}


class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr

    model_config = {"populate_by_name": True}


class TagResponse(BaseModel):
    id: int
    name: str
    color: Optional[str] = None

    model_config = {"populate_by_name": True}


class TaskResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[date] = Field(None, alias="dueDate")
    status: TaskStatus
    project_id: int = Field(..., alias="projectId")
    assignee: Optional[UserResponse] = None
    tags: List[TagResponse] = []
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")

    model_config = {"populate_by_name": True}


class ProjectWithMembersAndTasksResponse(BaseModel):
    id: int
    name: str
    status: ProjectStatus
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")
    members: List[UserResponse] = []
    tasks: List[TaskResponse] = []

    model_config = {"populate_by_name": True}


# Association models (for relationships)
class ProjectMember(BaseModel):
    project_id: int = Field(..., alias="projectId")
    user_id: int = Field(..., alias="userId")

    model_config = {"populate_by_name": True}


class TaskTag(BaseModel):
    task_id: int = Field(..., alias="taskId")
    tag_id: int = Field(..., alias="tagId")

    model_config = {"populate_by_name": True}