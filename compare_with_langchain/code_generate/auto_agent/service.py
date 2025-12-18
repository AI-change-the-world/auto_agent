from typing import Optional, List
from models import (
    BaseSchema,
    CreateUserRequest,
    UpdateUserRequest,
    UserResponse,
    UserListResponse,
    CreateProjectRequest,
    UpdateProjectRequest,
    ProjectResponse,
    ProjectListResponse,
    EmptyResponse
)
from abc import ABC, abstractmethod
import uuid
from datetime import datetime


# 定义自定义异常
class NotFoundException(Exception):
    pass


class BaseService(ABC):
    """基础服务类，提供通用功能"""
    pass


class UserRepository(ABC):
    """用户数据访问接口（用于依赖注入）"""

    @abstractmethod
    async def get_user_by_id(self, user_id: int) -> Optional[dict]:
        pass

    @abstractmethod
    async def get_all_users(self, page: int, size: int) -> List[dict]:
        pass

    @abstractmethod
    async def create_user(self, user_data: dict) -> dict:
        pass

    @abstractmethod
    async def update_user(self, user_id: int, user_data: dict) -> dict:
        pass

    @abstractmethod
    async def delete_user(self, user_id: int) -> bool:
        pass

    @abstractmethod
    async def get_total_user_count(self) -> int:
        pass


class ProjectRepository(ABC):
    """项目数据访问接口（用于依赖注入）"""

    @abstractmethod
    async def get_project_by_id(self, project_id: int) -> Optional[dict]:
        pass

    @abstractmethod
    async def get_projects_by_owner(self, owner_id: int, page: int, size: int) -> List[dict]:
        pass

    @abstractmethod
    async def get_all_projects(self, page: int, size: int) -> List[dict]:
        pass

    @abstractmethod
    async def create_project(self, project_data: dict) -> dict:
        pass

    @abstractmethod
    async def update_project(self, project_id: int, project_data: dict) -> dict:
        pass

    @abstractmethod
    async def delete_project(self, project_id: int) -> bool:
        pass

    @abstractmethod
    async def get_total_project_count(self) -> int:
        pass

    @abstractmethod
    async def get_total_projects_by_owner(self, owner_id: int) -> int:
        pass


class UserService(BaseService):
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    async def get_users(self, page: int, size: int) -> UserListResponse:
        if page < 1 or size < 1:
            raise ValueError("Page and size must be positive integers")

        users_data = await self.user_repo.get_all_users(page, size)
        total = await self.user_repo.get_total_user_count()
        
        users = [
            UserResponse(
                id=user["id"],
                username=user["username"],
                email=user["email"],
                created_at=user["created_at"]
            )
            for user in users_data
        ]
        
        return UserListResponse(
            items=users,
            total=total,
            page=page,
            size=size
        )

    async def create_user(self, request: CreateUserRequest) -> UserResponse:
        # 模拟生成 UUID 和时间戳
        user_data = {
            "id": str(uuid.uuid4()),
            "username": request.username,
            "email": request.email,
            "password_hash": self._hash_password(request.password),
            "created_at": datetime.utcnow()
        }
        created_user = await self.user_repo.create_user(user_data)
        
        return UserResponse(
            id=created_user["id"],
            username=created_user["username"],
            email=created_user["email"],
            created_at=created_user["created_at"]
        )

    async def get_user_by_id(self, user_id: int) -> UserResponse:
        user_data = await self.user_repo.get_user_by_id(user_id)
        if not user_data:
            raise NotFoundException(f"User with ID {user_id} not found")
            
        return UserResponse(
            id=user_data["id"],
            username=user_data["username"],
            email=user_data["email"],
            created_at=user_data["created_at"]
        )

    async def update_user(self, user_id: int, request: UpdateUserRequest) -> UserResponse:
        user_data = {}
        if request.username is not None:
            user_data["username"] = request.username
        if request.email is not None:
            user_data["email"] = request.email
        if request.password is not None:
            user_data["password_hash"] = self._hash_password(request.password)

        if not user_data:
            # 如果没有提供任何更新字段，直接返回当前用户信息
            return await self.get_user_by_id(user_id)

        updated_user = await self.user_repo.update_user(user_id, user_data)
        if not updated_user:
            raise NotFoundException(f"User with ID {user_id} not found")
            
        return UserResponse(
            id=updated_user["id"],
            username=updated_user["username"],
            email=updated_user["email"],
            created_at=updated_user["created_at"]
        )

    async def delete_user(self, user_id: int) -> EmptyResponse:
        success = await self.user_repo.delete_user(user_id)
        if not success:
            raise NotFoundException(f"User with ID {user_id} not found")
        return EmptyResponse()

    def _hash_password(self, password: str) -> str:
        # 实际应用中应使用安全的哈希算法如 bcrypt
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest()


class ProjectService(BaseService):
    def __init__(self, project_repo: ProjectRepository, user_repo: UserRepository):
        self.project_repo = project_repo
        self.user_repo = user_repo

    async def get_projects(self, page: int, size: int) -> ProjectListResponse:
        if page < 1 or size < 1:
            raise ValueError("Page and size must be positive integers")

        projects_data = await self.project_repo.get_all_projects(page, size)
        total = await self.project_repo.get_total_project_count()
        
        projects = [
            ProjectResponse(
                id=project["id"],
                name=project["name"],
                description=project.get("description"),
                owner_id=project["owner_id"],
                created_at=project["created_at"]
            )
            for project in projects_data
        ]
        
        return ProjectListResponse(
            items=projects,
            total=total,
            page=page,
            size=size
        )

    async def create_project(self, request: CreateProjectRequest) -> ProjectResponse:
        # 验证用户是否存在
        owner_exists = await self.user_repo.get_user_by_id(request.owner_id)
        if not owner_exists:
            raise NotFoundException(f"User with ID {request.owner_id} not found")

        project_data = {
            "id": str(uuid.uuid4()),
            "name": request.name,
            "description": request.description,
            "owner_id": request.owner_id,
            "created_at": datetime.utcnow()
        }
        created_project = await self.project_repo.create_project(project_data)
        
        return ProjectResponse(
            id=created_project["id"],
            name=created_project["name"],
            description=created_project.get("description"),
            owner_id=created_project["owner_id"],
            created_at=created_project["created_at"]
        )

    async def get_project_by_id(self, project_id: int) -> ProjectResponse:
        project_data = await self.project_repo.get_project_by_id(project_id)
        if not project_data:
            raise NotFoundException(f"Project with ID {project_id} not found")
            
        return ProjectResponse(
            id=project_data["id"],
            name=project_data["name"],
            description=project_data.get("description"),
            owner_id=project_data["owner_id"],
            created_at=project_data["created_at"]
        )

    async def update_project(self, project_id: int, request: UpdateProjectRequest) -> ProjectResponse:
        project_data = {}
        if request.name is not None:
            project_data["name"] = request.name
        if request.description is not None:
            project_data["description"] = request.description

        if not project_data:
            # 如果没有提供任何更新字段，直接返回当前项目信息
            return await self.get_project_by_id(project_id)

        updated_project = await self.project_repo.update_project(project_id, project_data)
        if not updated_project:
            raise NotFoundException(f"Project with ID {project_id} not found")
            
        return ProjectResponse(
            id=updated_project["id"],
            name=updated_project["name"],
            description=updated_project.get("description"),
            owner_id=updated_project["owner_id"],
            created_at=updated_project["created_at"]
        )

    async def delete_project(self, project_id: int) -> EmptyResponse:
        success = await self.project_repo.delete_project(project_id)
        if not success:
            raise NotFoundException(f"Project with ID {project_id} not found")
        return EmptyResponse()

    async def get_user_projects(self, user_id: int, page: int, size: int) -> ProjectListResponse:
        if page < 1 or size < 1:
            raise ValueError("Page and size must be positive integers")

        # 验证用户是否存在
        user_exists = await self.user_repo.get_user_by_id(user_id)
        if not user_exists:
            raise NotFoundException(f"User with ID {user_id} not found")

        projects_data = await self.project_repo.get_projects_by_owner(user_id, page, size)
        total = await self.project_repo.get_total_projects_by_owner(user_id)
        
        projects = [
            ProjectResponse(
                id=project["id"],
                name=project["name"],
                description=project.get("description"),
                owner_id=project["owner_id"],
                created_at=project["created_at"]
            )
            for project in projects_data
        ]
        
        return ProjectListResponse(
            items=projects,
            total=total,
            page=page,
            size=size
        )