"""
数据库会话管理模块

提供 SQLAlchemy Engine 和 Session 工厂。
使用同步引擎（SQLite 本地项目），与三个参考项目保持一致。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# 同步引擎
engine = create_engine(
    settings.database_url,
    echo=False,
    future=True,
)

# 会话工厂
session_factory = sessionmaker(
    engine,
    class_=Session,
    expire_on_commit=False,
)


def get_db() -> Session:
    """
    获取数据库会话（FastAPI 依赖注入）

    用法：
        @app.get("/path")
        async def handler(db: Session = Depends(get_db)):
            ...

    :return: SQLAlchemy Session 对象
    """
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
