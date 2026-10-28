import asyncio
import json

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.research import search_web
from .engine import Run, WorkflowEngine, TERMINAL
from .models import ConnectionRequest, UserInput, WorkflowRequest, PersonaUpdate, PersonaRequest


def create_workflow_router(answer_fn, resolve_fn, installed_fn):
    router = APIRouter(prefix='/api/workflow', tags=['workflow'])
    runs = {}

    async def llm(_client, model, context, instruction, base_url, **options):
        async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=10)) as client:
            return await answer_fn(client, model, context, instruction, base_url, **options)

    engine = WorkflowEngine(llm, search_web)

    def find(run_id):
        if run_id not in runs:
            raise HTTPException(404, '运行记录不在当前服务中；可能服务已重启。浏览器保存的结果仍可查看和导出。')
        return runs[run_id]

    @router.post('/connections/inspect')
    async def inspect_connection(body: ConnectionRequest):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                models = await installed_fn(client, body.base_url)
                version_response = await client.get(f'{body.base_url}/api/version')
                version = version_response.json().get('version', 'unknown') if version_response.is_success else 'unknown'
            return {'models': models, 'base_url': body.base_url, 'version': version}
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise HTTPException(503, '无法连接这个本地 Ollama 服务，请检查地址、端口及模型列表。') from exc

    @router.post('/runs')
    async def start(body: WorkflowRequest):
        active = [r for r in runs.values() if r.state not in TERMINAL]
        if active:
            raise HTTPException(409, '已有一个流程正在运行。请先结束或停止它，避免本地显存竞争。')
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                default_url = await resolve_fn(client)
                catalogs = {}
                used = {agent_id for step in body.steps for agent_id in step.agent_ids}
                if body.optimization.enabled:
                    used.update(a.id for a in body.agents)
                for agent in body.agents:
                    if agent.id not in used:
                        continue
                    url = agent.base_url or default_url
                    if url not in catalogs:
                        catalogs[url] = {m['name'] for m in await installed_fn(client, url)}
                    if agent.model not in catalogs[url]:
                        raise HTTPException(422, f'成员「{agent.name}」的模型不在 {url} 上，请刷新成员库。')
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(503, '无法连接本地模型服务，请先启动 Ollama。') from exc
        if any(r.state not in TERMINAL for r in runs.values()):
            raise HTTPException(409, '已有流程正在运行。请先停止它。')
        # Retain recent runs for browser reconnects, without unbounded growth.
        for key in list(runs)[:-19]:
            if runs[key].state in TERMINAL:
                del runs[key]
        run = Run(body, default_url, step_states={s.id: 'pending' for s in body.steps})
        runs[run.id] = run
        run.task = asyncio.create_task(engine.execute(run))
        return run.snapshot()

    @router.get('/runs/{run_id}')
    async def snapshot(run_id: str):
        return find(run_id).snapshot()

    @router.post('/runs/{run_id}/messages')
    async def send_message(run_id: str, body: UserInput):
        run = find(run_id)
        if run.state in TERMINAL:
            raise HTTPException(409, '本次流程已结束，请保留结果并新建任务。')
        if run.inbox.qsize() >= 30:
            raise HTTPException(429, '待处理留言较多，请等待当前处理节点完成。')
        await run.emit('conversation', role='user', content=body.text)
        await run.inbox.put(body.text)
        return {'accepted': True, 'waiting_user': run.state == 'waiting_user'}

    def editable_personas(run):
        if run.state in TERMINAL or run.personas_locked:
            raise HTTPException(409, '本次画像评审已开始或流程已结束，画像已锁定；请在下一次运行修改。')
        if not run.plan.optimization.enabled:
            raise HTTPException(409, '本次运行没有开启画像反馈循环。')

    @router.put('/runs/{run_id}/personas')
    async def update_personas(run_id: str, body: PersonaUpdate):
        run=find(run_id)
        editable_personas(run)
        ids={a.id for a in run.plan.agents}
        if len({p.id for p in body.personas}) != len(body.personas) or any(p.agent_id not in ids for p in body.personas):
            raise HTTPException(422, '画像ID必须唯一，模型必须是本次启动时已接入的成员。')
        run.plan.optimization.personas=body.personas
        run.personas_revision+=1
        await run.emit('personas_updated',personas=[p.model_dump() for p in body.personas],
                       revision=run.personas_revision,locked=False,origin='manual')
        return {'accepted':True,'revision':run.personas_revision}

    @router.post('/runs/{run_id}/personas/generate')
    async def request_persona(run_id: str, body: PersonaRequest):
        run=find(run_id)
        editable_personas(run)
        reserved=len(run.plan.optimization.personas)+len(run.persona_requests)
        if not run.requirements_ready and run.plan.optimization.auto_generate:
            reserved=max(len(run.plan.optimization.personas),run.plan.optimization.persona_count)+len(run.persona_requests)
        if reserved>=4:
            raise HTTPException(409,'画像及待生成数量已达4位。')
        run.persona_requests.append(body)
        await run.emit('persona_request',state='queued',content='新增画像已排队，将在当前处理节点完成后根据最新需求生成。')
        return {'accepted':True}

    @router.post('/runs/{run_id}/cancel')
    async def cancel(run_id: str):
        run = find(run_id)
        if run.state not in TERMINAL and run.task:
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
            if run.state not in TERMINAL:
                await run.state_event('cancelled')
        return run.snapshot()

    @router.get('/runs/{run_id}/events')
    async def stream(run_id: str, request: Request, after: int = 0):
        run = find(run_id)
        if after < 0:
            raise HTTPException(422, '游标不能为负数。')
        async def generate():
            cursor = after
            while True:
                if await request.is_disconnected():
                    return
                async with run.changed:
                    pending = run.events[cursor:]
                    if not pending and run.state in TERMINAL:
                        return
                    if not pending:
                        try:
                            await asyncio.wait_for(run.changed.wait(), timeout=12)
                        except TimeoutError:
                            pass
                        pending = run.events[cursor:]
                if pending:
                    for item in pending:
                        cursor = item['seq']
                        yield json.dumps(item, ensure_ascii=False) + '\n'
                elif run.state not in TERMINAL:
                    yield json.dumps({'type': 'heartbeat'}) + '\n'
        return StreamingResponse(generate(), media_type='application/x-ndjson',
                                 headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @router.on_event('shutdown')
    async def shutdown():
        tasks = [r.task for r in runs.values() if r.task and not r.task.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    return router
