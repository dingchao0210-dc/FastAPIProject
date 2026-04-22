from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from qa_service import Question, answer_question, query_reservoir

def create_app() -> FastAPI:
    # 本模块提供三个能力：
    # 1) 基础健康检查；2) 指定水库节点查询；3) 规则驱动的图谱问答。
    application = FastAPI(title="水资源知识图谱 API")

    # 允许前端调用（开发环境允许所有来源）
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return application


app = create_app()

# 健康检查
@app.get("/ping")
def ping():
    return {"status": "ok"}

# 查询水库信息
@app.get("/reservoir/{name}")
def get_reservoir(name: str):
    return query_reservoir(name)


# 问答接口（先用简单规则）
@app.post("/ask")
def ask(q: Question):
    # API 仅负责接收问题与返回答案，具体问答流程由 answer_question 编排。
    return answer_question(q.text)
