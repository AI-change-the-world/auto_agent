from fastapi import FastAPI, Depends, HTTPException, status, Path, Body
from typing import List, Optional
from pydantic import BaseModel

# 假设模型类已定义在 models.py 中（此处为简化，内联部分关键模型）
# 实际项目中应从 models 模块导入

class ProjectStatus(str):
    pass

class TaskStatus(str):
    pass

class TaskPriority(int):
    pass

class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class ProjectResponse(ProjectBase):
    id: int
    status: ProjectStatus

class ProjectWithMembersAndTasksResponse(ProjectResponse):
    members: List["UserResponse"]
    tasks: List["TaskResponse"]

class UserBase(BaseModel):
    username: str
    email: str

class UserCreate(UserBase):
    pass

class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None

class UserResponse(UserBase):
    id: int

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    priority: Optional[TaskPriority] = None

class TaskCreate(TaskBase):
    assignee_id: Optional[int] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[TaskPriority] = None
    assignee_id: Optional[int] = None

class TaskResponse(TaskBase):
    id: int
    project_id: int
    status: TaskStatus
    assignee: Optional[UserResponse] = None

class TagBase(BaseModel):
    name: str
    color: Optional[str] = None

class TagCreate(TagBase):
    pass

class TagUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None

class TagResponse(TagBase):
    id: int

class ProjectMember(BaseModel):
    user_id: int
    role: Optional[str] = None

# 服务层模拟（实际应由依赖注入提供）
class ProjectService:
    async def get_all(self) -> List[ProjectResponse]:
        return []
    
    async def create(self, project: ProjectCreate) -> ProjectResponse:
        return ProjectResponse(id=1, name=project.name, description=project.description, status=ProjectStatus("active"))
    
    async def get_by_id(self, project_id: int) -> ProjectWithMembersAndTasksResponse:
        return ProjectWithMembersAndTasksResponse(
            id=project_id,
            name="Sample",
            description="",
            status=ProjectStatus("active"),
            members=[],
            tasks=[]
        )
    
    async def update(self, project_id: int, project: ProjectUpdate) -> ProjectResponse:
        return ProjectResponse(id=project_id, name="Updated", description="", status=ProjectStatus("active"))
    
    async def delete(self, project_id: int) -> bool:
        return True
    
    async def get_tasks_by_project_id(self, project_id: int) -> List[TaskResponse]:
        return []
    
    async def get_members_by_project_id(self, project_id: int) -> List[UserResponse]:
        return []
    
    async def add_member(self, project_id: int, user_id: int) -> bool:
        return True
    
    async def remove_member(self, project_id: int, user_id: int) -> bool:
        return True

class UserService:
    async def get_all(self) -> List[UserResponse]:
        return []
    
    async def get_by_id(self, user_id: int) -> UserResponse:
        return UserResponse(id=user_id, username="user", email="user@example.com")

class TaskService:
    async def get_by_id(self, task_id: int) -> TaskResponse:
        return TaskResponse(id=task_id, title="Task", description="", project_id=1, status=TaskStatus("todo"), priority=1)
    
    async def update(self, task_id: int, task: TaskUpdate) -> TaskResponse:
        return TaskResponse(id=task_id, title="Updated", description="", project_id=1, status=TaskStatus("todo"), priority=1)
    
    async def delete(self, task_id: int) -> bool:
        return True
    
    async def get_tags_by_task_id(self, task_id: int) -> List[TagResponse]:
        return []
    
    async def add_tag_to_task(self, task_id: int, tag_id: int) -> bool:
        return True
    
    async def remove_tag_from_task(self, task_id: int, tag_id: int) -> bool:
        return True

class TagService:
    async def get_all(self) -> List[TagResponse]:
        return []
    
    async def create(self, tag: TagCreate) -> TagResponse:
        return TagResponse(id=1, name=tag.name, color=tag.color)
    
    async def get_by_id(self, tag_id: int) -> TagResponse:
        return TagResponse(id=tag_id, name="tag", color="#000")
    
    async def update(self, tag_id: int, tag: TagUpdate) -> TagResponse:
        return TagResponse(id=tag_id, name="updated", color="#fff")
    
    async def delete(self, tag_id: int) -> bool:
        return True

# 依赖项
def get_project_service() -> ProjectService:
    return ProjectService()

def get_user_service() -> UserService:
    return UserService()

def get_task_service() -> TaskService:
    return TaskService()

def get_tag_service() -> TagService:
    return TagService()

app = FastAPI(
    title="Project Management API",
    description="API for managing projects, tasks, users and tags",
    version="1.0.0"
)

# Projects routes
@app.get("/projects", response_model=List[ProjectResponse], summary="获取项目列表")
async def get_projects(service: ProjectService = Depends(get_project_service)):
    return await service.get_all()

@app.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED, summary="创建新项目")
async def create_project(project: ProjectCreate, service: ProjectService = Depends(get_project_service)):
    return await service.create(project)

@app.get("/projects/{projectId}", response_model=ProjectWithMembersAndTasksResponse, summary="获取指定项目的详细信息")
async def get_project(
    projectId: int = Path(..., description="项目ID"),
    service: ProjectService = Depends(get_project_service)
):
    project = await service.get_by_id(projectId)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@app.put("/projects/{projectId}", response_model=ProjectResponse, summary="更新指定项目的信息")
async def update_project(
    projectId: int = Path(..., description="项目ID"),
    project: ProjectUpdate = Body(...),
    service: ProjectService = Depends(get_project_service)
):
    updated = await service.update(projectId, project)
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated

@app.delete("/projects/{projectId}", status_code=status.HTTP_204_NO_CONTENT, summary="删除指定项目")
async def delete_project(
    projectId: int = Path(..., description="项目ID"),
    service: ProjectService = Depends(get_project_service)
):
    success = await service.delete(projectId)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")
    return

@app.get("/projects/{projectId}/tasks", response_model=List[TaskResponse], summary="获取指定项目下的所有任务")
async def get_project_tasks(
    projectId: int = Path(..., description="项目ID"),
    service: ProjectService = Depends(get_project_service)
):
    return await service.get_tasks_by_project_id(projectId)

@app.post("/projects/{projectId}/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED, summary="在指定项目下创建新任务")
async def create_task_in_project(
    projectId: int = Path(..., description="项目ID"),
    task: TaskCreate = Body(...),
    service: TaskService = Depends(get_task_service)
):
    # Note: In real implementation, you'd validate projectId and associate task with it
    return await service.get_by_id(1)  # Placeholder

@app.get("/projects/{projectId}/members", response_model=List[UserResponse], summary="获取指定项目的所有成员")
async def get_project_members(
    projectId: int = Path(..., description="项目ID"),
    service: ProjectService = Depends(get_project_service)
):
    return await service.get_members_by_project_id(projectId)

@app.post("/projects/{projectId}/members", status_code=status.HTTP_204_NO_CONTENT, summary="向指定项目添加成员")
async def add_member_to_project(
    projectId: int = Path(..., description="项目ID"),
    user_id: int = Body(..., embed=True, description="用户ID"),
    service: ProjectService = Depends(get_project_service)
):
    success = await service.add_member(projectId, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Project or user not found")
    return

@app.delete("/projects/{projectId}/members/{userId}", status_code=status.HTTP_204_NO_CONTENT, summary="从指定项目中移除成员")
async def remove_member_from_project(
    projectId: int = Path(..., description="项目ID"),
    userId: int = Path(..., description="用户ID"),
    service: ProjectService = Depends(get_project_service)
):
    success = await service.remove_member(projectId, userId)
    if not success:
        raise HTTPException(status_code=404, detail="Project or user not found")
    return

# Users routes
@app.get("/users", response_model=List[UserResponse], summary="获取用户列表")
async def get_users(service: UserService = Depends(get_user_service)):
    return await service.get_all()

@app.get("/users/{userId}", response_model=UserResponse, summary="获取指定用户的详细信息")
async def get_user(
    userId: int = Path(..., description="用户ID"),
    service: UserService = Depends(get_user_service)
):
    user = await service.get_by_id(userId)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# Tasks routes
@app.get("/tasks/{taskId}", response_model=TaskResponse, summary="获取指定任务的详细信息")
async def get_task(
    taskId: int = Path(..., description="任务ID"),
    service: TaskService = Depends(get_task_service)
):
    task = await service.get_by_id(taskId)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.put("/tasks/{taskId}", response_model=TaskResponse, summary="更新指定任务的信息")
async def update_task(
    taskId: int = Path(..., description="任务ID"),
    task: TaskUpdate = Body(...),
    service: TaskService = Depends(get_task_service)
):
    updated = await service.update(taskId, task)
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    return updated

@app.delete("/tasks/{taskId}", status_code=status.HTTP_204_NO_CONTENT, summary="删除指定任务")
async def delete_task(
    taskId: int = Path(..., description="任务ID"),
    service: TaskService = Depends(get_task_service)
):
    success = await service.delete(taskId)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return

@app.get("/tasks/{taskId}/tags", response_model=List[TagResponse], summary="获取指定任务关联的所有标签")
async def get_task_tags(
    taskId: int = Path(..., description="任务ID"),
    service: TaskService = Depends(get_task_service)
):
    return await service.get_tags_by_task_id(taskId)

@app.post("/tasks/{taskId}/tags", status_code=status.HTTP_204_NO_CONTENT, summary="为指定任务添加标签")
async def add_tag_to_task(
    taskId: int = Path(..., description="任务ID"),
    tag_id: int = Body(..., embed=True, description="标签ID"),
    service: TaskService = Depends(get_task_service)
):
    success = await service.add_tag_to_task(taskId, tag_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task or tag not found")
    return

@app.delete("/tasks/{taskId}/tags/{tagId}", status_code=status.HTTP_204_NO_CONTENT, summary="从指定任务中移除指定标签")
async def remove_tag_from_task(
    taskId: int = Path(..., description="任务ID"),
    tagId: int = Path(..., description="标签ID"),
    service: TaskService = Depends(get_task_service)
):
    success = await service.remove_tag_from_task(taskId, tagId)
    if not success:
        raise HTTPException(status_code=404, detail="Task or tag not found")
    return

# Tags routes
@app.get("/tags", response_model=List[TagResponse], summary="获取所有标签列表")
async def get_tags(service: TagService = Depends(get_tag_service)):
    return await service.get_all()

@app.post("/tags", response_model=TagResponse, status_code=status.HTTP_201_CREATED, summary="创建新标签")
async def create_tag(tag: TagCreate, service: TagService = Depends(get_tag_service)):
    return await service.create(tag)

@app.get("/tags/{tagId}", response_model=TagResponse, summary="获取指定标签的详细信息")
async def get_tag(
    tagId: int = Path(..., description="标签ID"),
    service: TagService = Depends(get_tag_service)
):
    tag = await service.get_by_id(tagId)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag

@app.put("/tags/{tagId}", response_model=TagResponse, summary="更新指定标签的信息")
async def update_tag(
    tagId: int = Path(..., description="标签ID"),
    tag: TagUpdate = Body(...),
    service: TagService = Depends(get_tag_service)
):
    updated = await service.update(tagId, tag)
    if not updated:
        raise HTTPException(status_code=404, detail="Tag not found")
    return updated

@app.delete("/tags/{tagId}", status_code=status.HTTP_204_NO_CONTENT, summary="删除指定标签")
async def delete_tag(
    tagId: int = Path(..., description="标签ID"),
    service: TagService = Depends(get_tag_service)
):
    success = await service.delete(tagId)
    if not success:
        raise HTTPException(status_code=404, detail="Tag not found")
    return