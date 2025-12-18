from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List, Optional
from pydantic import BaseModel

# 假设服务类和模型类已定义在其他模块中，这里仅做导入示意
# 实际使用时应替换为正确的模块路径
from .models import (
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
from .services import get_user_service, get_project_service  # 假设的依赖注入函数

router = APIRouter()


# 用户相关路由
@router.get(
    "/users",
    response_model=UserListResponse,
    summary="获取用户列表",
    description="获取分页的用户列表"
)
async def get_users_route(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    user_service = Depends(get_user_service)
):
    try:
        users = await user_service.get_users(page=page, size=size)
        total = await user_service.get_total_user_count()
        return UserListResponse(users=users, total=total, page=page, size=size)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建新用户",
    description="创建一个新的用户账户"
)
async def create_user_route(
    user_data: CreateUserRequest,
    user_service = Depends(get_user_service)
):
    try:
        user = await user_service.create_user(user_data)
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/users/{id}",
    response_model=UserResponse,
    summary="获取单个用户信息",
    description="根据用户ID获取用户详细信息"
)
async def get_user_by_id_route(
    id: int,
    user_service = Depends(get_user_service)
):
    try:
        user = await user_service.get_user_by_id(id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put(
    "/users/{id}",
    response_model=UserResponse,
    summary="更新用户信息",
    description="根据用户ID更新用户信息"
)
async def update_user_route(
    id: int,
    user_data: UpdateUserRequest,
    user_service = Depends(get_user_service)
):
    try:
        user = await user_service.update_user(id, user_data)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete(
    "/users/{id}",
    response_model=EmptyResponse,
    summary="删除用户",
    description="根据用户ID删除用户"
)
async def delete_user_route(
    id: int,
    user_service = Depends(get_user_service)
):
    try:
        success = await user_service.delete_user(id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        return EmptyResponse()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/users/{id}/projects",
    response_model=ProjectListResponse,
    summary="获取指定用户拥有的所有项目",
    description="获取指定用户拥有的分页项目列表"
)
async def get_user_projects_route(
    id: int,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    project_service = Depends(get_project_service)
):
    try:
        projects = await project_service.get_projects_by_owner(owner_id=id, page=page, size=size)
        total = await project_service.get_total_projects_by_owner(owner_id=id)
        return ProjectListResponse(projects=projects, total=total, page=page, size=size)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# 项目相关路由
@router.get(
    "/projects",
    response_model=ProjectListResponse,
    summary="获取项目列表",
    description="获取分页的项目列表"
)
async def get_projects_route(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    project_service = Depends(get_project_service)
):
    try:
        projects = await project_service.get_all_projects(page=page, size=size)
        total = await project_service.get_total_project_count()
        return ProjectListResponse(projects=projects, total=total, page=page, size=size)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建新项目",
    description="创建一个新的项目"
)
async def create_project_route(
    project_data: CreateProjectRequest,
    project_service = Depends(get_project_service)
):
    try:
        project = await project_service.create_project(project_data)
        return project
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/projects/{id}",
    response_model=ProjectResponse,
    summary="获取单个项目信息",
    description="根据项目ID获取项目详细信息"
)
async def get_project_by_id_route(
    id: int,
    project_service = Depends(get_project_service)
):
    try:
        project = await project_service.get_project_by_id(id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        return project
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put(
    "/projects/{id}",
    response_model=ProjectResponse,
    summary="更新项目信息",
    description="根据项目ID更新项目信息"
)
async def update_project_route(
    id: int,
    project_data: UpdateProjectRequest,
    project_service = Depends(get_project_service)
):
    try:
        project = await project_service.update_project(id, project_data)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        return project
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete(
    "/projects/{id}",
    response_model=EmptyResponse,
    summary="删除项目",
    description="根据项目ID删除项目"
)
async def delete_project_route(
    id: int,
    project_service = Depends(get_project_service)
):
    try:
        success = await project_service.delete_project(id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        return EmptyResponse()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))