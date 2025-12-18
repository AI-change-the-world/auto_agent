from typing import List, Optional
from datetime import datetime, date

# Enums (assuming these are defined elsewhere; included here for completeness)
from enum import Enum

class ProjectStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"

class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"

class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

# Base models (simplified as dataclasses or Pydantic models would be used in practice)
# For this service layer, we assume they are just type hints

class ProjectBase:
    id: str
    name: str
    status: ProjectStatus
    createdAt: datetime
    updatedAt: Optional[datetime]

class UserBase:
    id: str
    username: str
    email: str

class TaskBase:
    id: str
    title: str
    description: Optional[str]
    priority: Optional[TaskPriority]
    dueDate: Optional[date]
    status: TaskStatus
    projectId: str
    assigneeId: Optional[str]
    createdAt: datetime
    updatedAt: Optional[datetime]

class TagBase:
    id: str
    name: str
    color: Optional[str]

# Create/Update/Response models (assumed to exist with appropriate fields)

class ProjectCreate:
    name: str
    status: ProjectStatus

class ProjectUpdate:
    name: Optional[str] = None
    status: Optional[ProjectStatus] = None

class UserCreate:
    username: str
    email: str

class UserUpdate:
    username: Optional[str] = None
    email: Optional[str] = None

class TaskCreate:
    title: str
    description: Optional[str] = None
    priority: Optional[TaskPriority] = None
    dueDate: Optional[date] = None
    status: TaskStatus
    assigneeId: Optional[str] = None

class TaskUpdate:
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[TaskPriority] = None
    dueDate: Optional[date] = None
    status: Optional[TaskStatus] = None
    assigneeId: Optional[str] = None

class TagCreate:
    name: str
    color: Optional[str] = None

class TagUpdate:
    name: Optional[str] = None
    color: Optional[str] = None

class ProjectResponse(ProjectBase):
    pass

class UserResponse(UserBase):
    pass

class TaskResponse(TaskBase):
    pass

class TagResponse(TagBase):
    pass

class ProjectMember:
    projectId: str
    userId: str

class TaskTag:
    taskId: str
    tagId: str

class ProjectWithMembersAndTasksResponse(ProjectBase):
    members: List[UserResponse]
    tasks: List[TaskResponse]


# Mock repositories (in real code, these would be injected)
class ProjectRepository:
    async def get_all(self) -> List[ProjectBase]: ...
    async def create(self, project: ProjectCreate) -> ProjectBase: ...
    async def get_by_id(self, project_id: str) -> Optional[ProjectBase]: ...
    async def update(self, project_id: str, update_data: ProjectUpdate) -> Optional[ProjectBase]: ...
    async def delete(self, project_id: str) -> bool: ...
    async def get_tasks_by_project_id(self, project_id: str) -> List[TaskBase]: ...
    async def get_members_by_project_id(self, project_id: str) -> List[UserBase]: ...
    async def add_member(self, project_id: str, user_id: str) -> bool: ...
    async def remove_member(self, project_id: str, user_id: str) -> bool: ...

class UserRepository:
    async def get_all(self) -> List[UserBase]: ...
    async def get_by_id(self, user_id: str) -> Optional[UserBase]: ...

class TaskRepository:
    async def create(self, task: TaskCreate, project_id: str) -> TaskBase: ...
    async def get_by_id(self, task_id: str) -> Optional[TaskBase]: ...
    async def update(self, task_id: str, update_data: TaskUpdate) -> Optional[TaskBase]: ...
    async def delete(self, task_id: str) -> bool: ...
    async def get_tags_by_task_id(self, task_id: str) -> List[TagBase]: ...
    async def add_tag_to_task(self, task_id: str, tag_id: str) -> bool: ...
    async def remove_tag_from_task(self, task_id: str, tag_id: str) -> bool: ...

class TagRepository:
    async def get_all(self) -> List[TagBase]: ...
    async def create(self, tag: TagCreate) -> TagBase: ...
    async def get_by_id(self, tag_id: str) -> Optional[TagBase]: ...
    async def update(self, tag_id: str, update_data: TagUpdate) -> Optional[TagBase]: ...
    async def delete(self, tag_id: str) -> bool: ...


# Service Layer
class ProjectService:
    def __init__(
        self,
        project_repo: ProjectRepository,
        user_repo: UserRepository,
        task_repo: TaskRepository,
        tag_repo: TagRepository
    ):
        self.project_repo = project_repo
        self.user_repo = user_repo
        self.task_repo = task_repo
        self.tag_repo = tag_repo

    async def get_projects(self) -> List[ProjectResponse]:
        projects = await self.project_repo.get_all()
        return [ProjectResponse(**p.__dict__) if hasattr(p, '__dict__') else p for p in projects]

    async def create_project(self, project_create: ProjectCreate) -> ProjectResponse:
        project = await self.project_repo.create(project_create)
        return ProjectResponse(**project.__dict__) if hasattr(project, '__dict__') else project

    async def get_project_by_id(self, project_id: str) -> Optional[ProjectWithMembersAndTasksResponse]:
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            return None

        members = await self.project_repo.get_members_by_project_id(project_id)
        tasks = await self.project_repo.get_tasks_by_project_id(project_id)

        member_responses = [
            UserResponse(**m.__dict__) if hasattr(m, '__dict__') else m for m in members
        ]
        task_responses = [
            TaskResponse(**t.__dict__) if hasattr(t, '__dict__') else t for t in tasks
        ]

        return ProjectWithMembersAndTasksResponse(
            **project.__dict__,
            members=member_responses,
            tasks=task_responses
        )

    async def update_project(self, project_id: str, project_update: ProjectUpdate) -> Optional[ProjectResponse]:
        updated = await self.project_repo.update(project_id, project_update)
        if not updated:
            return None
        return ProjectResponse(**updated.__dict__) if hasattr(updated, '__dict__') else updated

    async def delete_project(self, project_id: str) -> bool:
        return await self.project_repo.delete(project_id)

    async def get_project_tasks(self, project_id: str) -> List[TaskResponse]:
        tasks = await self.project_repo.get_tasks_by_project_id(project_id)
        return [TaskResponse(**t.__dict__) if hasattr(t, '__dict__') else t for t in tasks]

    async def create_task_in_project(self, project_id: str, task_create: TaskCreate) -> TaskResponse:
        task = await self.task_repo.create(task_create, project_id)
        return TaskResponse(**task.__dict__) if hasattr(task, '__dict__') else task

    async def get_project_members(self, project_id: str) -> List[UserResponse]:
        members = await self.project_repo.get_members_by_project_id(project_id)
        return [UserResponse(**m.__dict__) if hasattr(m, '__dict__') else m for m in members]

    async def add_member_to_project(self, project_id: str, user_id: str) -> bool:
        # Optional: validate user exists
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return False
        return await self.project_repo.add_member(project_id, user_id)

    async def remove_member_from_project(self, project_id: str, user_id: str) -> bool:
        return await self.project_repo.remove_member(project_id, user_id)


class UserService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    async def get_users(self) -> List[UserResponse]:
        users = await self.user_repo.get_all()
        return [UserResponse(**u.__dict__) if hasattr(u, '__dict__') else u for u in users]

    async def get_user_by_id(self, user_id: str) -> Optional[UserResponse]:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None
        return UserResponse(**user.__dict__) if hasattr(user, '__dict__') else user


class TaskService:
    def __init__(self, task_repo: TaskRepository, tag_repo: TagRepository):
        self.task_repo = task_repo
        self.tag_repo = tag_repo

    async def get_task_by_id(self, task_id: str) -> Optional[TaskResponse]:
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            return None
        return TaskResponse(**task.__dict__) if hasattr(task, '__dict__') else task

    async def update_task(self, task_id: str, task_update: TaskUpdate) -> Optional[TaskResponse]:
        updated = await self.task_repo.update(task_id, task_update)
        if not updated:
            return None
        return TaskResponse(**updated.__dict__) if hasattr(updated, '__dict__') else updated

    async def delete_task(self, task_id: str) -> bool:
        return await self.task_repo.delete(task_id)

    async def get_task_tags(self, task_id: str) -> List[TagResponse]:
        tags = await self.task_repo.get_tags_by_task_id(task_id)
        return [TagResponse(**t.__dict__) if hasattr(t, '__dict__') else t for t in tags]

    async def add_tag_to_task(self, task_id: str, tag_id: str) -> bool:
        # Optional: validate tag exists
        tag = await self.tag_repo.get_by_id(tag_id)
        if not tag:
            return False
        return await self.task_repo.add_tag_to_task(task_id, tag_id)

    async def remove_tag_from_task(self, task_id: str, tag_id: str) -> bool:
        return await self.task_repo.remove_tag_from_task(task_id, tag_id)


class TagService:
    def __init__(self, tag_repo: TagRepository):
        self.tag_repo = tag_repo

    async def get_tags(self) -> List[TagResponse]:
        tags = await self.tag_repo.get_all()
        return [TagResponse(**t.__dict__) if hasattr(t, '__dict__') else t for t in tags]

    async def create_tag(self, tag_create: TagCreate) -> TagResponse:
        tag = await self.tag_repo.create(tag_create)
        return TagResponse(**tag.__dict__) if hasattr(tag, '__dict__') else tag

    async def get_tag_by_id(self, tag_id: str) -> Optional[TagResponse]:
        tag = await self.tag_repo.get_by_id(tag_id)
        if not tag:
            return None
        return TagResponse(**tag.__dict__) if hasattr(tag, '__dict__') else tag

    async def update_tag(self, tag_id: str, tag_update: TagUpdate) -> Optional[TagResponse]:
        updated = await self.tag_repo.update(tag_id, tag_update)
        if not updated:
            return None
        return TagResponse(**updated.__dict__) if hasattr(updated, '__dict__') else updated

    async def delete_tag(self, tag_id: str) -> bool:
        return await self.tag_repo.delete(tag_id)