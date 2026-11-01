FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

# 依赖预装进镜像，代码通过 volume 挂载，改代码不用重建镜像
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    fastapi "uvicorn[standard]" pandas openpyxl

CMD ["python", "-m", "ops_automation.api"]
