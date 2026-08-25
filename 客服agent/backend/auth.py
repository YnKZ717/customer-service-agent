"""JWT 认证模块"""
import os
import jwt
import hashlib
from datetime import datetime, timedelta
from fastapi import HTTPException, Depends, Header
from typing import Optional

# JWT 密钥（生产环境应该用环境变量）
JWT_SECRET = os.getenv("JWT_SECRET", "neowow-customer-service-2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 7  # Token 有效期 7 天

# 用户数据库（本地简易版）
# 实际应该从数据库读取
USERS = {
    "admin": {
        "password": "admin123",
        "role": "admin",
        "name": "管理员",
    },
    "support": {
        "password": "support123",
        "role": "support",
        "name": "客服人员",
    },
    "user": {
        "password": "user123",
        "role": "user",
        "name": "普通用户",
    },
}


def hash_password(password: str) -> str:
    """密码哈希"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """验证密码"""
    return hash_password(password) == hashed


def create_token(username: str, role: str, name: str) -> str:
    """创建 JWT Token"""
    payload = {
        "username": username,
        "role": role,
        "name": name,
        "exp": datetime.utcnow() + timedelta(days=JWT_EXPIRE_DAYS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """解析 JWT Token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的 Token")


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """从请求头获取当前用户"""
    if not authorization:
        raise HTTPException(status_code=401, detail="缺少认证信息")

    # 支持 "Bearer xxx" 格式
    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization[7:]

    return decode_token(token)


def require_role(*roles: str):
    """权限检查装饰器"""
    def dependency(user: dict = Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="权限不足")
        return user
    return dependency
