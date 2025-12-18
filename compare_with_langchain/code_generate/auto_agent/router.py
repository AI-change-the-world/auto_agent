from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Query
from typing import Optional, List
from pydantic import BaseModel

# Import models
from models import (
    ProjectStatusEnum,
    CreateProjectRequest,
    UpdateProjectRequest,
    ProjectResponse,
    ProjectListResponse,
    UserResponse,
    UserListResponse,
    AddProjectMemberRequest,
    ProjectMemberResponse,
    ProjectMemberListResponse,
    CreateTaskRequest,
    UpdateTaskRequest,
    TaskResponse,
    TaskListResponse,
    CreateTagRequest,
    UpdateTagRequest,
    TagResponse,
    TagListResponse,
    AddTaskTagRequest,
    TaskTagResponse,
    CreateCommentRequest,
    UpdateCommentRequest,
    CommentResponse,
    CommentListResponse,
    CreateAttachmentRequest,
    AttachmentResponse,
    AttachmentListResponse,
    EmptyResponse,
)

# Import services
from services import (
    get_projects,
    create_project,
    get_project,
    update_project,
    delete_project,
    get_users,
    get_user,
    get_project_members,
    add_project_member,
    remove_project_member,
    get_project_tasks,
    create_task,
    get_task,
    update_task,
    delete_task,
    get_subtasks,
    get_project_tags,
    create_tag,
    get_tag,
    update_tag,
    delete_tag,
    add_task_tag,
    remove_task_tag,
    get_task_comments,
    create_comment,
    get_comment,
    update_comment,
    delete_comment,
    get_task_attachments,
    create_attachment,
    get_attachment,
    delete_attachment,
    download_attachment,
)


router = APIRouter()


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
    status: Optional[str] = None,
):
    try:
        return await get_projects(page=page, size=size, status=status)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建新项目",
    description="创建新项目"
)
async def create_new_project(project_data: CreateProjectRequest):
    try:
        return await create_project(project_data)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/projects/{id}",
    response_model=ProjectResponse,
    summary="获取单个项目详情",
    description="获取单个项目详情"
)
async def get_single_project(id: int):
    try:
        project = await get_project(id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return project
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put(
    "/projects/{id}",
    response_model=ProjectResponse,
    summary="更新项目信息",
    description="更新项目信息"
)
async def update_single_project(id: int, project_data: UpdateProjectRequest):
    try:
        project = await update_project(id, project_data)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return project
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete(
    "/projects/{id}",
    response_model=EmptyResponse,
    summary="删除项目（软删除或级联逻辑由后端处理）",
    description="删除项目（软删除或级联逻辑由后端处理）"
)
async def delete_single_project(id: int):
    try:
        result = await delete_project(id)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return EmptyResponse()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# Project members endpoints
@router.get(
    "/projects/{project_id}/members",
    response_model=ProjectMemberListResponse,
    summary="获取项目成员列表",
    description="获取项目成员列表"
)
async def list_project_members(project_id: int):
    try:
        return await get_project_members(project_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/projects/{project_id}/members",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="向项目添加成员",
    description="向项目添加成员"
)
async def add_member_to_project(project_id: int, member_data: AddProjectMemberRequest):
    try:
        return await add_project_member(project_id, member_data)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete(
    "/projects/{project_id}/members/{user_id}",
    response_model=EmptyResponse,
    summary="从项目中移除成员",
    description="从项目中移除成员"
)
async def remove_member_from_project(project_id: int, user_id: int):
    try:
        result = await remove_project_member(project_id, user_id)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found in project")
        return EmptyResponse()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# Users endpoints
@router.get(
    "/users",
    response_model=UserListResponse,
    summary="获取用户列表",
    description="获取用户列表"
)
async def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
):
    try:
        return await get_users(page=page, size=size)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/users/{id}",
    response_model=UserResponse,
    summary="获取单个用户",
    description="获取单个用户"
)
async def get_single_user(id: int):
    try:
        user = await get_user(id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# Tasks endpoints
@router.get(
    "/projects/{project_id}/tasks",
    response_model=TaskListResponse,
    summary="获取项目下的任务列表（可选过滤父任务、状态等）",
    description="获取项目下的任务列表（可选过滤父任务、状态等）"
)
async def list_project_tasks(
    project_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    parent_task_id: Optional[int] = None,
    status: Optional[str] = None,
    assignee_id: Optional[int] = None,
):
    try:
        return await get_project_tasks(
            project_id=project_id,
            page=page,
            size=size,
            parent_task_id=parent_task_id,
            status=status,
            assignee_id=assignee_id
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/projects/{project_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="在项目中创建新任务",
    description="在项目中创建新任务"
)
async def create_new_task(project_id: int, task_data: CreateTaskRequest):
    try:
        return await create_task(project_id, task_data)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/tasks/{id}",
    response_model=TaskResponse,
    summary="获取单个任务详情",
    description="获取单个任务详情"
)
async def get_single_task(id: int):
    try:
        task = await get_task(id)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return task
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put(
    "/tasks/{id}",
    response_model=TaskResponse,
    summary="更新任务信息",
    description="更新任务信息"
)
async def update_single_task(id: int, task_data: UpdateTaskRequest):
    try:
        task = await update_task(id, task_data)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return task
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete(
    "/tasks/{id}",
    response_model=EmptyResponse,
    summary="删除任务（及其子任务）",
    description="删除任务（及其子任务）"
)
async def delete_single_task(id: int):
    try:
        result = await delete_task(id)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return EmptyResponse()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/tasks/{task_id}/subtasks",
    response_model=TaskListResponse,
    summary="获取任务的子任务列表",
    description="获取任务的子任务列表"
)
async def list_subtasks(task_id: int):
    try:
        return await get_subtasks(task_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# Tags endpoints
@router.get(
    "/projects/{project_id}/tags",
    response_model=TagListResponse,
    summary="获取项目下的标签列表",
    description="获取项目下的标签列表"
)
async def list_project_tags(project_id: int):
    try:
        return await get_project_tags(project_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/projects/{project_id}/tags",
    response_model=TagResponse,
    status_code=status.HTTP_201_CREATED,
    summary="在项目中创建新标签",
    description="在项目中创建新标签"
)
async def create_new_tag(project_id: int, tag_data: CreateTagRequest):
    try:
        return await create_tag(project_id, tag_data)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/tags/{id}",
    response_model=TagResponse,
    summary="获取单个标签",
    description="获取单个标签"
)
async def get_single_tag(id: int):
    try:
        tag = await get_tag(id)
        if not tag:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
        return tag
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put(
    "/tags/{id}",
    response_model=TagResponse,
    summary="更新标签信息",
    description="更新标签信息"
)
async def update_single_tag(id: int, tag_data: UpdateTagRequest):
    try:
        tag = await update_tag(id, tag_data)
        if not tag:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
        return tag
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete(
    "/tags/{id}",
    response_model=EmptyResponse,
    summary="删除标签（自动解除与任务的关联）",
    description="删除标签（自动解除与任务的关联）"
)
async def delete_single_tag(id: int):
    try:
        result = await delete_tag(id)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
        return EmptyResponse()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# Task tags endpoints
@router.post(
    "/tasks/{task_id}/tags",
    response_model=TaskTagResponse,
    status_code=status.HTTP_201_CREATED,
    summary="为任务添加标签",
    description="为任务添加标签"
)
async def add_tag_to_task(task_id: int, tag_data: AddTaskTagRequest):
    try:
        return await add_task_tag(task_id, tag_data)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete(
    "/tasks/{task_id}/tags/{tag_id}",
    response_model=EmptyResponse,
    summary="从任务中移除标签",
    description="从任务中移除标签"
)
async def remove_tag_from_task(task_id: int, tag_id: int):
    try:
        result = await remove_task_tag(task_id, tag_id)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not associated with task")
        return EmptyResponse()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# Comments endpoints
@router.get(
    "/tasks/{task_id}/comments",
    response_model=CommentListResponse,
    summary="获取任务下的评论列表",
    description="获取任务下的评论列表"
)
async def list_task_comments(task_id: int):
    try:
        return await get_task_comments(task_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/tasks/{task_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="在任务下创建新评论",
    description="在任务下创建新评论"
)
async def create_new_comment(task_id: int, comment_data: CreateCommentRequest):
    try:
        return await create_comment(task_id, comment_data)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/comments/{id}",
    response_model=CommentResponse,
    summary="获取单条评论",
    description="获取单条评论"
)
async def get_single_comment(id: int):
    try:
        comment = await get_comment(id)
        if not comment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
        return comment
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put(
    "/comments/{id}",
    response_model=CommentResponse,
    summary="更新评论内容",
    description="更新评论内容"
)
async def update_single_comment(id: int, comment_data: UpdateCommentRequest):
    try:
        comment = await update_comment(id, comment_data)
        if not comment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
        return comment
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete(
    "/comments/{id}",
    response_model=EmptyResponse,
    summary="删除评论",
    description="删除评论"
)
async def delete_single_comment(id: int):
    try:
        result = await delete_comment(id)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
        return EmptyResponse()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# Attachments endpoints
@router.get(
    "/tasks/{task_id}/attachments",
    response_model=AttachmentListResponse,
    summary="获取任务下的附件列表",
    description="获取任务下的附件列表"
)
async def list_task_attachments(task_id: int):
    try:
        return await get_task_attachments(task_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/tasks/{task_id}/attachments",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="上传附件到任务（multipart/form-data）",
    description="上传附件到任务（multipart/form-data）"
)
async def upload_attachment(task_id: int, file: UploadFile = File(...)):
    try:
        attachment_data = CreateAttachmentRequest(filename=file.filename, content_type=file.content_type)
        return await create_attachment(task_id, attachment_data, file)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/attachments/{id}",
    response_model=AttachmentResponse,
    summary="获取单个附件元数据",
    description="获取单个附件元数据"
)
async def get_single_attachment(id: int):
    try:
        attachment = await get_attachment(id)
        if not attachment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
        return attachment
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete(
    "/attachments/{id}",
    response_model=EmptyResponse,
    summary="删除附件",
    description="删除附件"
)
async def delete_single_attachment(id: int):
    try:
        result = await delete_attachment(id)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
        return EmptyResponse()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/attachments/{id}/download",
    summary="下载附件文件",
    description="下载附件文件"
)
async def download_single_attachment(id: int):
    try:
        file_response = await download_attachment(id)
        if not file_response:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
        return file_response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))