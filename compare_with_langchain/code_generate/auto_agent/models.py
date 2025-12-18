from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class BaseSchema(BaseModel):
    """基础模型配置，所有模型继承此类"""
    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
        "arbitrary_types_allowed": True
    }


# User 模型
class CreateUserRequest(BaseSchema):
    """
    创建用户的请求模型
    
    用于用户注册时的输入验证
    """
    username: str = Field(..., description="用户名，唯一")
    email: str = Field(..., description="用户邮箱，唯一")
    password: str = Field(..., description="用户密码")


class UpdateUserRequest(BaseSchema):
    """
    更新用户的请求模型
    
    用于用户信息更新，所有字段均为可选
    """
    username: Optional[str] = Field(None, description="用户名，唯一")
    email: Optional[str] = Field(None, description="用户邮箱，唯一")
    password: Optional[str] = Field(None, description="用户密码")


class UserResponse(BaseSchema):
    """
    用户响应模型
    
    用于返回用户信息，不包含敏感字段如密码哈希
    """
    id: int = Field(..., description="用户唯一标识符")
    username: str = Field(..., description="用户名，唯一")
    email: str = Field(..., description="用户邮箱，唯一")
    created_at: datetime = Field(..., description="账户创建时间")


class UserListResponse(BaseSchema):
    """
    用户列表响应模型
    
    用于分页返回用户列表
    """
    items: List[UserResponse] = Field(..., description="用户列表")
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    size: int = Field(..., description="每页大小")


# Project 模型
class CreateProjectRequest(BaseSchema):
    """
    创建项目的请求模型
    
    用于项目创建时的输入验证
    """
    name: str = Field(..., description="项目名称")
    description: Optional[str] = Field(None, description="项目描述")
    owner_id: int = Field(..., description="项目所有者用户ID")


class UpdateProjectRequest(BaseSchema):
    """
    更新项目的请求模型
    
    用于项目信息更新，所有字段均为可选
    """
    name: Optional[str] = Field(None, description="项目名称")
    description: Optional[str] = Field(None, description="项目描述")


class ProjectResponse(BaseSchema):
    """
    项目响应模型
    
    用于返回项目信息
    """
    id: int = Field(..., description="项目唯一标识符")
    name: str = Field(..., description="项目名称")
    description: Optional[str] = Field(None, description="项目描述")
    owner_id: int = Field(..., description="项目所有者用户ID")
    created_at: datetime = Field(..., description="项目创建时间")


class ProjectListResponse(BaseSchema):
    """
    项目列表响应模型
    
    用于分页返回项目列表
    """
    items: List[ProjectResponse] = Field(..., description="项目列表")
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    size: int = Field(..., description="每页大小")


class EmptyResponse(BaseSchema):
    """
    空响应模型
    
    用于不需要返回数据的操作
    """
    pass