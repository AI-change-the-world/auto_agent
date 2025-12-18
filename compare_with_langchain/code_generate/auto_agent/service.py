from typing import List, Optional, Dict, Any
from uuid import UUID

from models import (
    BaseSchema,
    ProjectStatusEnum,
    ProjectBase,
    CreateProjectRequest,
    UpdateProjectRequest,
    ProjectResponse,
    ProjectListResponse,
    UserBase,
    UserResponse,
    UserListResponse,
    ProjectMemberBase,
    AddProjectMemberRequest,
    ProjectMemberResponse,
    ProjectMemberListResponse,
    TaskStatusEnum,
    TaskPriorityEnum,
    TaskBase,
    CreateTaskRequest,
    UpdateTaskRequest,
    TaskResponse,
    TaskListResponse,
    TagBase,
    CreateTagRequest,
    UpdateTagRequest,
    TagResponse,
    TagListResponse,
    TaskTagBase,
    AddTaskTagRequest,
    TaskTagResponse,
    CommentBase,
    CreateCommentRequest,
    UpdateCommentRequest,
    CommentResponse,
    CommentListResponse,
    AttachmentBase,
    CreateAttachmentRequest,
    AttachmentResponse,
    AttachmentListResponse,
    EmptyResponse
)

# Custom exceptions
class NotFoundException(Exception):
    pass

class BadRequestException(Exception):
    pass

class ForbiddenException(Exception):
    pass


class BaseService:
    def __init__(self, db_session: Any):
        self.db = db_session


class ProjectService(BaseService):
    async def get_projects(
        self,
        page: int = 1,
        size: int = 10,
        status: Optional[str] = None
    ) -> ProjectListResponse:
        # Implementation would query the database with filters and pagination
        pass

    async def create_project(self, request: CreateProjectRequest) -> ProjectResponse:
        # Implementation would validate and create a new project
        pass

    async def get_project(self, id: int) -> ProjectResponse:
        # Implementation would fetch a single project by ID
        pass

    async def update_project(self, id: int, request: UpdateProjectRequest) -> ProjectResponse:
        # Implementation would update project details
        pass

    async def delete_project(self, id: int) -> EmptyResponse:
        # Implementation would soft-delete or cascade delete the project
        pass


class UserService(BaseService):
    async def get_users(
        self,
        page: int = 1,
        size: int = 10
    ) -> UserListResponse:
        # Implementation would query users with pagination
        pass

    async def get_user(self, id: int) -> UserResponse:
        # Implementation would fetch a single user by ID
        pass


class ProjectMemberService(BaseService):
    async def get_project_members(self, project_id: int) -> ProjectMemberListResponse:
        # Implementation would fetch all members of a project
        pass

    async def add_project_member(
        self,
        project_id: int,
        request: AddProjectMemberRequest
    ) -> ProjectMemberResponse:
        # Implementation would add a user as a member to the project
        pass

    async def remove_project_member(self, project_id: int, user_id: int) -> EmptyResponse:
        # Implementation would remove a user from the project
        pass


class TaskService(BaseService):
    async def get_project_tasks(
        self,
        project_id: int,
        page: int = 1,
        size: int = 10,
        parent_task_id: Optional[int] = None,
        status: Optional[str] = None,
        assignee_id: Optional[int] = None
    ) -> TaskListResponse:
        # Implementation would fetch tasks under a project with optional filters
        pass

    async def create_task(self, project_id: int, request: CreateTaskRequest) -> TaskResponse:
        # Implementation would create a new task in the project
        pass

    async def get_task(self, id: int) -> TaskResponse:
        # Implementation would fetch a single task by ID
        pass

    async def update_task(self, id: int, request: UpdateTaskRequest) -> TaskResponse:
        # Implementation would update task details
        pass

    async def delete_task(self, id: int) -> EmptyResponse:
        # Implementation would delete the task and its subtasks
        pass

    async def get_subtasks(self, task_id: int) -> TaskListResponse:
        # Implementation would fetch all direct subtasks of a task
        pass


class TagService(BaseService):
    async def get_project_tags(self, project_id: int) -> TagListResponse:
        # Implementation would fetch all tags under a project
        pass

    async def create_tag(self, project_id: int, request: CreateTagRequest) -> TagResponse:
        # Implementation would create a new tag in the project
        pass

    async def get_tag(self, id: int) -> TagResponse:
        # Implementation would fetch a single tag by ID
        pass

    async def update_tag(self, id: int, request: UpdateTagRequest) -> TagResponse:
        # Implementation would update tag details
        pass

    async def delete_tag(self, id: int) -> EmptyResponse:
        # Implementation would delete the tag and dissociate from tasks
        pass


class TaskTagService(BaseService):
    async def add_task_tag(
        self,
        task_id: int,
        request: AddTaskTagRequest
    ) -> TaskTagResponse:
        # Implementation would associate a tag with a task
        pass

    async def remove_task_tag(self, task_id: int, tag_id: int) -> EmptyResponse:
        # Implementation would dissociate a tag from a task
        pass


class CommentService(BaseService):
    async def get_task_comments(self, task_id: int) -> CommentListResponse:
        # Implementation would fetch all comments under a task
        pass

    async def create_comment(self, task_id: int, request: CreateCommentRequest) -> CommentResponse:
        # Implementation would create a new comment on the task
        pass

    async def get_comment(self, id: int) -> CommentResponse:
        # Implementation would fetch a single comment by ID
        pass

    async def update_comment(self, id: int, request: UpdateCommentRequest) -> CommentResponse:
        # Implementation would update comment content
        pass

    async def delete_comment(self, id: int) -> EmptyResponse:
        # Implementation would delete the comment
        pass


class AttachmentService(BaseService):
    async def get_task_attachments(self, task_id: int) -> AttachmentListResponse:
        # Implementation would fetch all attachments under a task
        pass

    async def create_attachment(
        self,
        task_id: int,
        request: CreateAttachmentRequest
    ) -> AttachmentResponse:
        # Implementation would handle file upload and store metadata
        pass

    async def get_attachment(self, id: int) -> AttachmentResponse:
        # Implementation would fetch attachment metadata by ID
        pass

    async def delete_attachment(self, id: int) -> EmptyResponse:
        # Implementation would delete the attachment metadata and file
        pass

    async def download_attachment(self, id: int) -> bytes:
        # Implementation would return file content for download
        pass