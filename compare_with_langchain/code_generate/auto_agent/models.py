from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, EmailStr, Field


class BaseSchema(BaseModel):
    """基础 Pydantic 模型配置"""

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
    status: ProjectStatusEnum = Field(
        ..., description="项目状态：进行中、已完成、已归档"
    )


class CreateProjectRequest(ProjectBase):
    """创建项目请求模型"""

    pass


class UpdateProjectRequest(BaseSchema):
    """更新项目请求模型"""

    name: Optional[str] = Field(None, description="项目名称")
    description: Optional[str] = Field(None, description="项目描述")
    status: Optional[ProjectStatusEnum] = Field(
        None, description="项目状态：进行中、已完成、已归档"
    )


class ProjectResponse(ProjectBase):
    """项目响应模型"""

    id: int = Field(..., description="项目唯一标识符")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")


class ProjectListResponse(BaseSchema):
    """项目列表响应模型"""

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


class UserResponse(UserBase):
    """用户响应模型"""

    id: int = Field(..., description="用户唯一标识符")


class UserListResponse(BaseSchema):
    """用户列表响应模型"""

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
    """添加项目成员请求模型"""

    user_id: int = Field(..., description="成员用户ID")
    role: Optional[str] = Field(None, description="成员在项目中的角色（可选）")


class ProjectMemberResponse(ProjectMemberBase):
    """项目成员响应模型"""

    user: UserResponse


class ProjectMemberListResponse(BaseSchema):
    """项目成员列表响应模型"""

    items: List[ProjectMemberResponse]


# ======================
# Task Models
# ======================


class TaskStatusEnum(str):
    TODO = "待办"
    IN_PROGRESS = "进行中"
    COMPLETED = "已完成"


class TaskPriorityEnum(str):
    LOW = "低"
    MEDIUM = "中"
    HIGH = "高"


class TaskBase(BaseSchema):
    project_id: int = Field(..., description="所属项目ID")
    parent_task_id: Optional[int] = Field(None, description="父任务ID（用于子任务）")
    title: str = Field(..., description="任务标题")
    description: Optional[str] = Field(None, description="任务描述")
    priority: Optional[TaskPriorityEnum] = Field(
        None, description="任务优先级（如低、中、高）"
    )
    due_date: Optional[date] = Field(None, description="截止日期")
    status: TaskStatusEnum = Field(..., description="任务状态：待办、进行中、已完成")
    assignee_id: Optional[int] = Field(None, description="分配给的用户ID")


class CreateTaskRequest(TaskBase):
    """创建任务请求模型"""

    pass


class UpdateTaskRequest(BaseSchema):
    """更新任务请求模型"""

    parent_task_id: Optional[int] = Field(None, description="父任务ID（用于子任务）")
    title: Optional[str] = Field(None, description="任务标题")
    description: Optional[str] = Field(None, description="任务描述")
    priority: Optional[TaskPriorityEnum] = Field(
        None, description="任务优先级（如低、中、高）"
    )
    due_date: Optional[date] = Field(None, description="截止日期")
    status: Optional[TaskStatusEnum] = Field(
        None, description="任务状态：待办、进行中、已完成"
    )
    assignee_id: Optional[int] = Field(None, description="分配给的用户ID")


class TaskResponse(TaskBase):
    """任务响应模型"""

    id: int = Field(..., description="任务唯一标识符")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")
    assignee: Optional[UserResponse] = None


class TaskListResponse(BaseSchema):
    """任务列表响应模型"""

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
    project_id: int = Field(..., description="所属项目ID")


class CreateTagRequest(BaseSchema):
    """创建标签请求模型"""

    name: str = Field(..., description="标签名称")
    color: Optional[str] = Field(None, description="标签颜色（可选）")


class UpdateTagRequest(BaseSchema):
    """更新标签请求模型"""

    name: Optional[str] = Field(None, description="标签名称")
    color: Optional[str] = Field(None, description="标签颜色（可选）")


class TagResponse(TagBase):
    """标签响应模型"""

    id: int = Field(..., description="标签唯一标识符")


class TagListResponse(BaseSchema):
    """标签列表响应模型"""

    items: List[TagResponse]


# ======================
# TaskTag Models
# ======================


class TaskTagBase(BaseSchema):
    task_id: int = Field(..., description="任务ID")
    tag_id: int = Field(..., description="标签ID")


class AddTaskTagRequest(BaseSchema):
    """添加任务标签请求模型"""

    tag_id: int = Field(..., description="标签ID")


class TaskTagResponse(TaskTagBase):
    """任务标签响应模型"""

    tag: TagResponse


# ======================
# Comment Models
# ======================


class CommentBase(BaseSchema):
    task_id: int = Field(..., description="所属任务ID")
    author_id: int = Field(..., description="评论作者ID")
    content: str = Field(..., description="评论内容")


class CreateCommentRequest(BaseSchema):
    """创建评论请求模型"""

    content: str = Field(..., description="评论内容")


class UpdateCommentRequest(BaseSchema):
    """更新评论请求模型"""

    content: str = Field(..., description="评论内容")


class CommentResponse(CommentBase):
    """评论响应模型"""

    id: int = Field(..., description="评论唯一标识符")
    created_at: datetime = Field(..., description="评论时间")
    author: UserResponse


class CommentListResponse(BaseSchema):
    """评论列表响应模型"""

    items: List[CommentResponse]


# ======================
# Attachment Models
# ======================


class AttachmentBase(BaseSchema):
    task_id: int = Field(..., description="所属任务ID")
    uploader_id: int = Field(..., description="上传者ID")
    file_name: str = Field(..., description="原始文件名")
    file_path: str = Field(..., description="服务器存储路径或URL")
    file_size: int = Field(..., description="文件大小（字节）")


class CreateAttachmentRequest(BaseSchema):
    """创建附件请求模型（实际上传通常通过 multipart/form-data 处理）"""

    # Note: In practice, file uploads are handled differently (e.g., using UploadFile in FastAPI)
    pass


class AttachmentResponse(AttachmentBase):
    """附件响应模型"""

    id: int = Field(..., description="附件唯一标识符")
    uploaded_at: datetime = Field(..., description="上传时间")
    uploader: UserResponse


class AttachmentListResponse(BaseSchema):
    """附件列表响应模型"""

    items: List[AttachmentResponse]


# ======================
# Generic Response Models
# ======================


class EmptyResponse(BaseSchema):
    """空响应模型"""

    pass
