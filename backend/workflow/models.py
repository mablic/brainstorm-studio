import ipaddress
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal

SEARCH_AGENT = 'web-researcher'


def local_url(value):
    if value is None:
        return value
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('请输入本机或局域网 Ollama 的 http(s) 地址。')
    if parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise ValueError('只需填写服务根地址，例如 http://127.0.0.1:11435。')
    host = parsed.hostname.lower()
    if host != 'localhost':
        try:
            address = ipaddress.ip_address(host)
            if not (address.is_loopback or address.is_private) or address.is_unspecified or address.is_multicast:
                raise ValueError()
        except ValueError as exc:
            raise ValueError('仅支持 localhost、本机或局域网 IP；不连接云端 AI。') from exc
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError('端口无效。') from exc
    return value.rstrip('/')


class Agent(BaseModel):
    id: str = Field(min_length=1, max_length=250)
    name: str = Field(min_length=1, max_length=180)
    model: str = Field(min_length=1, max_length=200)
    base_url: str | None = None
    role: str = Field(default='', max_length=2000)

    _local_url = field_validator('base_url')(local_url)


class Step(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=100)
    kind: Literal['personas', 'feedback', 'clarify', 'research', 'discussion', 'summary', 'custom']
    instructions: str = Field(default='', max_length=12000)
    agent_ids: list[str] = Field(default_factory=list, max_length=9)
    allow_web: bool = False
    rounds: int = Field(default=2, ge=1, le=4)


class Revision(BaseModel):
    previous_result: str = Field(min_length=1, max_length=60000)
    feedback: str = Field(min_length=1, max_length=20000)
    requirements: str = Field(default='', max_length=20000)
    evidence: str = Field(default='', max_length=30000)
    user_inputs: list[str] = Field(default_factory=list, max_length=100)

    @field_validator('user_inputs')
    @classmethod
    def bounded_inputs(cls, value):
        if sum(len(x) for x in value) > 20000:
            raise ValueError('历次真实补充超过20000字，请新建任务并填写需要保留的约束。')
        return value

    @field_validator('previous_result', 'feedback')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('上一版成果和修改反馈不能为空。')
        return value.strip()


class Persona(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    profile: str = Field(min_length=10, max_length=4000)
    agent_id: str = Field(min_length=1, max_length=250)


class Optimization(BaseModel):
    enabled: bool = False
    rounds: int = Field(default=1, ge=1, le=5)
    personas: list[Persona] = Field(default_factory=list, max_length=4)
    auto_generate: bool = False
    persona_count: int = Field(default=3, ge=1, le=4)


class PersonaUpdate(BaseModel):
    personas: list[Persona] = Field(min_length=1, max_length=4)


class PersonaRequest(BaseModel):
    hint: str = Field(default='', max_length=2000)


class WorkflowRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=20000)
    steps: list[Step] = Field(min_length=1, max_length=12)
    agents: list[Agent] = Field(min_length=1, max_length=40)
    revision: Revision | None = None
    optimization: Optimization = Field(default_factory=Optimization)
    depth: Literal['standard', 'decision'] = 'standard'
    language: Literal['zh', 'en'] = 'zh'

    @model_validator(mode='after')
    def validate_plan(self):
        ids = [a.id for a in self.agents]
        if len(set(ids)) != len(ids) or SEARCH_AGENT in ids:
            raise ValueError('AI 成员 ID 必须唯一，且不能使用搜索工具的保留 ID。')
        if len({s.id for s in self.steps}) != len(self.steps):
            raise ValueError('步骤 ID 必须唯一。')
        if self.steps[0].kind not in ('personas','clarify'):
            raise ValueError('第一步必须是自动生成画像或需求澄清。')
        for index, step in enumerate(self.steps):
            if len(set(step.agent_ids)) != len(step.agent_ids):
                raise ValueError('同一步骤不能重复加入同一成员。')
            if any(a not in ids and a != SEARCH_AGENT for a in step.agent_ids):
                raise ValueError(f'步骤「{step.title}」包含不可用成员。')
            local_members = [a for a in step.agent_ids if a != SEARCH_AGENT]
            if index == 0:
                if len(local_members) != 1 or SEARCH_AGENT in step.agent_ids or step.allow_web:
                    raise ValueError('需求澄清必须由一个本地 AI 负责，不联网。')
            elif step.kind in ('clarify','personas'):
                raise ValueError('需求澄清只作为第一步。')
            if not local_members and step.kind != 'feedback' and not (step.kind == 'research' and step.allow_web and SEARCH_AGENT in step.agent_ids):
                raise ValueError(f'请为步骤「{step.title}」分配 AI。')
        if not self.goal.strip():
            raise ValueError('请输入初始任务。')
        if any(s.kind=='feedback' for s in self.steps):
            if self.steps[-1].kind!='feedback' or sum(s.kind=='feedback' for s in self.steps)!=1 or not any(s.kind=='summary' for s in self.steps[:-1]):
                raise ValueError('模拟反馈节点必须在成果交付后，且作为最后一个节点。')
        if self.depth == 'decision' and self.steps[-1].kind not in ('summary','feedback'):
            raise ValueError('深度决策需要以成果交付结束，请先补齐决策流程。')
        if self.optimization.enabled:
            if not self.optimization.personas and not self.optimization.auto_generate:
                raise ValueError('请配置至少一个模拟客户画像。')
            if len({p.id for p in self.optimization.personas}) != len(self.optimization.personas):
                raise ValueError('模拟画像 ID 必须唯一。')
            if any(p.agent_id not in ids for p in self.optimization.personas):
                raise ValueError('模拟画像使用了不可用的模型。')
            if self.steps[-1].kind not in ('summary','feedback'):
                raise ValueError('启用画像优化时，最后一步必须是成果交付。')
        return self


class ConnectionRequest(BaseModel):
    base_url: str
    _local_url = field_validator('base_url')(local_url)


class UserInput(BaseModel):
    text: str = Field(min_length=1, max_length=20000)

    @field_validator('text')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('留言不能为空。')
        return value.strip()


class WorkOutput(BaseModel):
    answer: str = Field(min_length=10, max_length=10000)
    research_tasks: list[str] = Field(default_factory=list, max_length=3)
