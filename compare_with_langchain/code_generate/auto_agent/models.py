from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr


class BaseSchema(BaseModel):
    """基础模型配置"""
    model_config = {"from_attributes": True}


# ======================
# Project Models
# ======================

class ProjectStatusEnum(str):
    IN_PROGRESS = "进行中"
    COMPLETED = "已完成"
    ARCHIVED = "已归档"


class ProjectBase(BaseSchema):
    name: str = Field(..., description="项目名称")
    description: Optional[str] = Field(None, description="项目描述")
    status: ProjectStatusEnum = Field(..., description="项目状态：进行中、已完成、已归档")


class CreateProjectRequest(ProjectBase):
    """创建项目请求"""
    pass


class UpdateProjectRequest(BaseSchema):
    """更新项目请求"""
    name: Optional[str] = Field(None, description="项目名称")
    description: Optional[str] = Field(None, description="项目描述")
    status: Optional[ProjectStatusEnum] = Field(None, description="项目状态：进行中、已完成、已归档")


class ProjectResponse(ProjectBase):
    """项目响应"""
    id: int = Field(..., description="项目唯一标识符")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")


class ProjectListResponse(BaseSchema):
    """项目列表响应"""
    items: List[ProjectResponse]
    total: int
    page: int
    size: int


# ======================
# User Models
# ======================

class UserBase(BaseSchema):
    username: str = Field(..., description="用户名")
    email: EmailStr = Field(..., description="用户邮箱")


class CreateUserRequest(UserBase):
    """创建用户请求"""
    pass


class UpdateUserRequest(BaseSchema):
    """更新用户请求"""
    username: Optional[str] = Field(None, description="用户名")
    email: Optional[EmailStr] = Field(None, description="用户邮箱")


class UserResponse(UserBase):
    """用户响应"""
    id: int = Field(..., description="用户唯一标识符")


class UserListResponse(BaseSchema):
    """用户列表响应"""
    items: List[UserResponse]
    total: int
    page: int
    size: int


# ======================
# ProjectMember Models
# ======================

class ProjectMemberBase(BaseSchema):
    project_id: int = Field(..., description="所属项目ID")
    user_id: int = Field(..., description="成员用户ID")
    role: Optional[str] = Field(None, description="成员在项目中的角色（可选）")


class AddProjectMemberRequest(BaseSchema):
    """添加项目成员请求"""
    user_id: int = Field(..., description="成员用户ID")
    role: Optional[str] = Field(None, description="成员在项目中的角色（可选）")


class ProjectMemberResponse(ProjectMemberBase):
    """项目成员响应"""
    pass


class ProjectMemberListResponse(BaseSchema):
    """项目成员列表响应"""
    items: List[ProjectMemberResponse]


# ======================
# Task Models
# ======================

class TaskPriorityEnum(str):
    LOW = "低"
    MEDIUM = "中"
    HIGH = "高"


class TaskStatusEnum(str):
    TODO = "待办"
    IN_PROGRESS = "进行中"
    COMPLETED = "已完成"


class TaskBase(BaseSchema):
    title: str = Field(..., description="任务标题")
    description: Optional[str] = Field(None, description="任务描述")
    priority: TaskPriorityEnum = Field(..., description="任务优先级（如：低、中、高）")
    due_date: Optional[date] = Field(None, description="截止日期")
    status: TaskStatusEnum = Field(..., description="任务状态：待办、进行中、已完成")
    assignee_id: Optional[int] = Field(None, description="分配给的用户ID")


class CreateTaskRequest(TaskBase):
    """创建任务请求"""
    project_id: int = Field(..., description="所属项目ID")
    parent_task_id: Optional[int] = Field(None, description="父任务ID（用于子任务）")


class CreateSubtaskRequest(TaskBase):
    """创建子任务请求"""
    pass


class UpdateTaskRequest(BaseSchema):
    """更新任务请求"""
    title: Optional[str] = Field(None, description="任务标题")
    description: Optional[str] = Field(None, description="任务描述")
    priority: Optional[TaskPriorityEnum] = Field(None, description="任务优先级（如：低、中、高）")
    due_date: Optional[date] = Field(None, description="截止日期")
    status: Optional[TaskStatusEnum] = Field(None, description="任务状态：待办、进行中、已完成")
    assignee_id: Optional[int] = Field(None, description="分配给的用户ID")


class TaskResponse(TaskBase):
    """任务响应"""
    id: int = Field(..., description="任务唯一标识符")
    project_id: int = Field(..., description="所属项目ID")
    parent_task_id: Optional[int] = Field(None, description="父任务ID（用于子任务）")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")


class TaskListResponse(BaseSchema):
    """任务列表响应"""
    items: List[TaskResponse]
    total: int
    page: int
    size: int


# ======================
# Tag Models
# ======================

class TagBase(BaseSchema):
    name: str = Field(..., description="标签名称")
    color: Optional[str] = Field(None, description="标签颜色（可选）")


class CreateTagRequest(TagBase):
    """创建标签请求"""
    pass


class UpdateTagRequest(BaseSchema):
    """更新标签请求"""
    name: Optional[str] = Field(None, description="标签名称")
    color: Optional[str] = Field(None, description="标签颜色（可选）")


class TagResponse(TagBase):
    """标签响应"""
    id: int = Field(..., description="标签唯一标识符")


class TagListResponse(BaseSchema):
    """标签列表响应"""
    items: List[TagResponse]
    total: int
    page: int
    size: int


# ======================
# TaskTag Models
# ======================

class TaskTagBase(BaseSchema):
    task_id: int = Field(..., description="任务ID")
    tag_id: int = Field(..., description="标签ID")


class AddTaskTagRequest(BaseSchema):
    """添加任务标签请求"""
    tag_id: int = Field(..., description="标签ID")


class TaskTagResponse(TaskTagBase):
    """任务标签响应"""
    pass


# ======================
# Comment Models
# ======================

class CommentBase(BaseSchema):
    content: str = Field(..., description="评论内容")


class CreateCommentRequest(CommentBase):
    """创建评论请求"""
    pass


class UpdateCommentRequest(CommentBase):
    """更新评论请求"""
    pass


class CommentResponse(CommentBase):
    """评论响应"""
    id: int = Field(..., description="评论唯一标识符")
    task_id: int = Field(..., description="所属任务ID")
    author_id: int = Field(..., description="评论作者用户ID")
    created_at: datetime = Field(..., description="评论时间")


class CommentListResponse(BaseSchema):
    """评论列表响应"""
    items: List[CommentResponse]
    total: int
    page: int
    size: int


# ======================
# Attachment Models
# ======================

class AttachmentBase(BaseSchema):
    file_name: str = Field(..., description="原始文件名")
    file_path: str = Field(..., description="存储路径或URL")


class CreateAttachmentRequest(AttachmentBase):
    """创建附件请求"""
    pass


class AttachmentResponse(AttachmentBase):
    """附件响应"""
    id: int = Field(..., description="附件唯一标识符")
    task_id: int = Field(..., description="所属任务ID")
    uploaded_by: int = Field(..., description="上传者用户ID")
    uploaded_at: datetime = Field(..., description="上传时间")


class AttachmentListResponse(BaseSchema):
    """附件列表响应"""
    items: List[AttachmentResponse]


# ======================
# Empty Response
# ======================

class EmptyResponse(BaseSchema):
    """空响应"""
    pass