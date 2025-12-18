from fastapi import APIRouter, Depends, Query, Path, HTTPException, status
from typing import List, Optional

# Import models
from app.models import (
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
    TaskPriorityEnum,
    TaskStatusEnum,
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

# Import services
from app.services import (
    get_projects, create_project, get_project, update_project, delete_project,
    get_users, get_user,
    get_project_members, add_project_member, remove_project_member,
    get_tasks, create_task, get_task, update_task, delete_task, get_subtasks,
    get_tags, create_tag, get_tag, update_tag, delete_tag,
    get_task_tags, add_task_tag, remove_task_tag,
    get_task_comments, create_comment, get_comment, update_comment, delete_comment,
    get_task_attachments, create_attachment, get_attachment, delete_attachment
)

# Import auth dependency (assuming it's defined elsewhere)
from app.dependencies import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])


# Projects endpoints
@router.get(
    "/projects",
    response_model=ProjectListResponse,
    summary="获取项目列表",
    description="获取项目列表"
)
async def list_projects(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    status: Optional[str] = Query(None)
):
    return await get_projects(page=page, size=size, status=status)


@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建新项目",
    description="创建新项目"
)
async def create_new_project(project_data: CreateProjectRequest):
    return await create_project(project_data)


@router.get(
    "/projects/{id}",
    response_model=ProjectResponse,
    summary="获取单个项目详情",
    description="获取单个项目详情"
)
async def get_single_project(id: int = Path(..., gt=0)):
    project = await get_project(id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.put(
    "/projects/{id}",
    response_model=ProjectResponse,
    summary="更新项目信息",
    description="更新项目信息"
)
async def update_single_project(
    id: int = Path(..., gt=0),
    project_data: UpdateProjectRequest = None
):
    project = await update_project(id, project_data)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.delete(
    "/projects/{id}",
    response_model=EmptyResponse,
    summary="删除项目",
    description="删除项目"
)
async def delete_single_project(id: int = Path(..., gt=0)):
    success = await delete_project(id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return EmptyResponse()


# Project members endpoints
@router.get(
    "/projects/{project_id}/members",
    response_model=ProjectMemberListResponse,
    summary="获取项目成员列表",
    description="获取项目成员列表"
)
async def list_project_members(project_id: int = Path(..., gt=0)):
    return await get_project_members(project_id)


@router.post(
    "/projects/{project_id}/members",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="向项目添加成员",
    description="向项目添加成员"
)
async def add_member_to_project(
    project_id: int = Path(..., gt=0),
    member_data: AddProjectMemberRequest = None
):
    return await add_project_member(project_id, member_data)


@router.delete(
    "/projects/{project_id}/members/{user_id}",
    response_model=EmptyResponse,
    summary="从项目中移除成员",
    description="从项目中移除成员"
)
async def remove_member_from_project(
    project_id: int = Path(..., gt=0),
    user_id: int = Path(..., gt=0)
):
    success = await remove_project_member(project_id, user_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found in project")
    return EmptyResponse()


# Users endpoints
@router.get(
    "/users",
    response_model=UserListResponse,
    summary="获取用户列表",
    description="获取用户列表"
)
async def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100)
):
    return await get_users(page=page, size=size)


@router.get(
    "/users/{id}",
    response_model=UserResponse,
    summary="获取单个用户",
    description="获取单个用户"
)
async def get_single_user(id: int = Path(..., gt=0)):
    user = await get_user(id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


# Tasks endpoints
@router.get(
    "/tasks",
    response_model=TaskListResponse,
    summary="获取任务列表（可按项目、状态等过滤）",
    description="获取任务列表（可按项目、状态等过滤）"
)
async def list_tasks(
    project_id: Optional[int] = Query(None, gt=0),
    status: Optional[str] = Query(None),
    assignee_id: Optional[int] = Query(None, gt=0),
    parent_task_id: Optional[int] = Query(None, gt=0),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100)
):
    return await get_tasks(
        project_id=project_id,
        status=status,
        assignee_id=assignee_id,
        parent_task_id=parent_task_id,
        page=page,
        size=size
    )


@router.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建新任务",
    description="创建新任务"
)
async def create_new_task(task_data: CreateTaskRequest):
    return await create_task(task_data)


@router.get(
    "/tasks/{id}",
    response_model=TaskResponse,
    summary="获取单个任务详情",
    description="获取单个任务详情"
)
async def get_single_task(id: int = Path(..., gt=0)):
    task = await get_task(id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.put(
    "/tasks/{id}",
    response_model=TaskResponse,
    summary="更新任务信息",
    description="更新任务信息"
)
async def update_single_task(
    id: int = Path(..., gt=0),
    task_data: UpdateTaskRequest = None
):
    task = await update_task(id, task_data)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.delete(
    "/tasks/{id}",
    response_model=EmptyResponse,
    summary="删除任务（及其子任务）",
    description="删除任务（及其子任务）"
)
async def delete_single_task(id: int = Path(..., gt=0)):
    success = await delete_task(id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return EmptyResponse()


@router.get(
    "/tasks/{task_id}/subtasks",
    response_model=TaskListResponse,
    summary="获取任务的子任务列表",
    description="获取任务的子任务列表"
)
async def list_subtasks(task_id: int = Path(..., gt=0)):
    return await get_subtasks(task_id)


# Tags endpoints
@router.get(
    "/tags",
    response_model=TagListResponse,
    summary="获取标签列表",
    description="获取标签列表"
)
async def list_tags(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100)
):
    return await get_tags(page=page, size=size)


@router.post(
    "/tags",
    response_model=TagResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建新标签",
    description="创建新标签"
)
async def create_new_tag(tag_data: CreateTagRequest):
    return await create_tag(tag_data)


@router.get(
    "/tags/{id}",
    response_model=TagResponse,
    summary="获取单个标签",
    description="获取单个标签"
)
async def get_single_tag(id: int = Path(..., gt=0)):
    tag = await get_tag(id)
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return tag


@router.put(
    "/tags/{id}",
    response_model=TagResponse,
    summary="更新标签信息",
    description="更新标签信息"
)
async def update_single_tag(
    id: int = Path(..., gt=0),
    tag_data: UpdateTagRequest = None
):
    tag = await update_tag(id, tag_data)
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return tag


@router.delete(
    "/tags/{id}",
    response_model=EmptyResponse,
    summary="删除标签",
    description="删除标签"
)
async def delete_single_tag(id: int = Path(..., gt=0)):
    success = await delete_tag(id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return EmptyResponse()


# Task tags endpoints
@router.get(
    "/tasks/{task_id}/tags",
    response_model=TagListResponse,
    summary="获取任务关联的标签列表",
    description="获取任务关联的标签列表"
)
async def list_task_tags(task_id: int = Path(..., gt=0)):
    return await get_task_tags(task_id)


@router.post(
    "/tasks/{task_id}/tags",
    response_model=TaskTagResponse,
    status_code=status.HTTP_201_CREATED,
    summary="为任务添加标签",
    description="为任务添加标签"
)
async def add_tag_to_task(
    task_id: int = Path(..., gt=0),
    tag_data: AddTaskTagRequest = None
):
    return await add_task_tag(task_id, tag_data)


@router.delete(
    "/tasks/{task_id}/tags/{tag_id}",
    response_model=EmptyResponse,
    summary="从任务中移除标签",
    description="从任务中移除标签"
)
async def remove_tag_from_task(
    task_id: int = Path(..., gt=0),
    tag_id: int = Path(..., gt=0)
):
    success = await remove_task_tag(task_id, tag_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not associated with task")
    return EmptyResponse()


# Comments endpoints
@router.get(
    "/tasks/{task_id}/comments",
    response_model=CommentListResponse,
    summary="获取任务的评论列表",
    description="获取任务的评论列表"
)
async def list_task_comments(task_id: int = Path(..., gt=0)):
    return await get_task_comments(task_id)


@router.post(
    "/tasks/{task_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="为任务添加评论",
    description="为任务添加评论"
)
async def create_task_comment(
    task_id: int = Path(..., gt=0),
    comment_data: CreateCommentRequest = None
):
    return await create_comment(task_id, comment_data)


@router.get(
    "/comments/{id}",
    response_model=CommentResponse,
    summary="获取单条评论",
    description="获取单条评论"
)
async def get_single_comment(id: int = Path(..., gt=0)):
    comment = await get_comment(id)
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    return comment


@router.put(
    "/comments/{id}",
    response_model=CommentResponse,
    summary="更新评论内容",
    description="更新评论内容"
)
async def update_single_comment(
    id: int = Path(..., gt=0),
    comment_data: UpdateCommentRequest = None
):
    comment = await update_comment(id, comment_data)
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    return comment


@router.delete(
    "/comments/{id}",
    response_model=EmptyResponse,
    summary="删除评论",
    description="删除评论"
)
async def delete_single_comment(id: int = Path(..., gt=0)):
    success = await delete_comment(id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    return EmptyResponse()


# Attachments endpoints
@router.get(
    "/tasks/{task_id}/attachments",
    response_model=AttachmentListResponse,
    summary="获取任务的附件列表",
    description="获取任务的附件列表"
)
async def list_task_attachments(task_id: int = Path(..., gt=0)):
    return await get_task_attachments(task_id)


@router.post(
    "/tasks/{task_id}/attachments",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="为任务上传附件",
    description="为任务上传附件"
)
async def create_task_attachment(
    task_id: int = Path(..., gt=0),
    attachment_data: CreateAttachmentRequest = None
):
    return await create_attachment(task_id, attachment_data)


@router.get(
    "/attachments/{id}",
    response_model=AttachmentResponse,
    summary="获取单个附件信息",
    description="获取单个附件信息"
)
async def get_single_attachment(id: int = Path(..., gt=0)):
    attachment = await get_attachment(id)
    if not attachment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    return attachment


@router.delete(
    "/attachments/{id}",
    response_model=EmptyResponse,
    summary="删除附件",
    description="删除附件"
)
async def delete_single_attachment(id: int = Path(..., gt=0)):
    success = await delete_attachment(id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    return EmptyResponse()