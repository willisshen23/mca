from types import SimpleNamespace

from openjiuwen.core.context_engine import (
    ContextEngine,
    ContextEngineConfig,
    DialogueCompressorConfig,
    MessageOffloaderConfig,
)
from openjiuwen.core.foundation.llm import (
    AssistantMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from openjiuwen.core.context_engine.processor.compressor import dialogue_compressor


def _tool_round(question: str, answer: str, tool_content: str):
    return [
        UserMessage(content=question),
        AssistantMessage(
            content="调用工具",
            tool_calls=[ToolCall(
                id=f"call-{question}", type="function", name="query", arguments="{}",
            )],
        ),
        ToolMessage(tool_call_id=f"call-{question}", content=tool_content),
        AssistantMessage(content=answer),
    ]


async def test_dialogue_compressor_replaces_historical_react_block(monkeypatch):
    calls = []

    class FakeModel:
        def __init__(self, *args, **kwargs):
            pass

        async def invoke(self, messages, **kwargs):
            calls.append(messages)
            return SimpleNamespace(
                content='{"blocks":[{"block_id":"react_1","summary":"保留目标和工具结论"}]}',
                parser_content={"blocks": [{"block_id": "react_1", "summary": "保留目标和工具结论"}]},
                usage_metadata={"total_tokens": 10},
            )

    monkeypatch.setattr(dialogue_compressor, "Model", FakeModel)
    engine = ContextEngine(ContextEngineConfig())
    context = await engine.create_context(processors=[(
        "DialogueCompressor",
        DialogueCompressorConfig(
            tokens_threshold=1,
            keep_last_round=False,
            compression_target_tokens=20,
        ),
    )])

    await context.add_messages(_tool_round("原始问题", "原始回答", "数据" * 500))

    messages = context.get_messages()
    assert len(calls) == 1
    assert len(messages) == 2
    assert messages[0].content == "原始问题"
    assert "[DIALOGUE_MEMORY_BLOCK]" in messages[1].content
    assert "保留目标和工具结论" in messages[1].content

    state = context.save_state()
    restored = await ContextEngine(ContextEngineConfig()).create_context()
    restored.load_state({"default_context_id": state})
    assert "保留目标和工具结论" in restored.get_messages()[1].content


async def test_message_offloader_preserves_raw_message_in_state():
    engine = ContextEngine(ContextEngineConfig())
    context = await engine.create_context(processors=[(
        "MessageOffloader",
        MessageOffloaderConfig(
            tokens_threshold=1,
            large_message_threshold=10,
            trim_size=3,
            keep_last_round=False,
            protected_tool_names=[],
        ),
    )])
    raw_content = "完整工具结果" * 100

    await context.add_messages(_tool_round("问题", "回答", raw_content))

    messages = context.get_messages()
    assert messages[2].content.startswith("完整工...")
    assert "[[OFFLOAD:" in messages[2].content
    state = context.save_state()
    offloaded = list(state["offload_messages"].values())
    assert len(offloaded) == 1
    assert offloaded[0][0].content == raw_content

    restored = await ContextEngine(ContextEngineConfig()).create_context()
    restored.load_state({"default_context_id": state})
    restored_raw = list(restored.save_state()["offload_messages"].values())
    assert restored_raw[0][0].content == raw_content


async def test_round_window_keeps_latest_complete_tool_round():
    engine = ContextEngine(ContextEngineConfig(default_window_round_num=1))
    context = await engine.create_context()
    await context.add_messages([
        UserMessage(content="旧问题"),
        AssistantMessage(content="旧回答"),
    ])
    latest = _tool_round("新问题", "新回答", "工具结果")
    await context.add_messages(latest)

    window = await context.get_context_window()

    assert len(context.get_messages()) == 6
    assert [message.content for message in window.get_messages()] == [
        message.content for message in latest
    ]
    assert window.get_messages()[1].tool_calls[0].id == window.get_messages()[2].tool_call_id


async def test_react_agent_uses_dialogue_compressor_before_main_model(monkeypatch):
    from openjiuwen.core.session.agent import create_agent_session
    from openjiuwen.core.single_agent import AgentCard, ReActAgent, ReActAgentConfig

    class FakeCompressionModel:
        def __init__(self, *args, **kwargs):
            pass

        async def invoke(self, messages, **kwargs):
            return SimpleNamespace(
                content="compressed",
                parser_content={"blocks": [{"block_id": "react_1", "summary": "历史任务摘要"}]},
                usage_metadata={},
            )

    monkeypatch.setattr(dialogue_compressor, "Model", FakeCompressionModel)
    main_calls = []

    class FakeMainModel:
        async def invoke(self, messages, **kwargs):
            main_calls.append(messages)
            return AssistantMessage(content="主模型回答")

    card = AgentCard(id="context-test-agent", description="context test")
    agent = ReActAgent(card=card).configure(ReActAgentConfig(
        max_iterations=2,
        context_engine_config=ContextEngineConfig(),
        context_processors=[(
            "DialogueCompressor",
            DialogueCompressorConfig(tokens_threshold=1, keep_last_round=True),
        )],
    ))
    agent.set_llm(FakeMainModel())
    session = create_agent_session(session_id="context-test", card=card)
    context = await agent._init_context(session)
    await context.add_messages(_tool_round("历史问题", "历史回答", "历史数据" * 500))
    await context.add_messages(_tool_round("最近问题", "最近回答", "最近数据"))

    result = await agent.invoke("新任务", session=session)

    assert result is not None
    assert len(main_calls) == 1
    contents = [message.content for message in main_calls[0]]
    assert any("[DIALOGUE_MEMORY_BLOCK]" in content and "历史任务摘要" in content for content in contents)
    assert "最近问题" in contents
    assert "新任务" in contents


async def test_filesystem_offload_reloads_through_read_file_with_sandbox(tmp_path):
    import re

    from openjiuwen.core.sys_operation import (
        LocalWorkConfig,
        OperationMode,
        SysOperation,
        SysOperationCard,
    )
    from openjiuwen.harness.tools import ReadFileTool
    from openjiuwen.harness.workspace.workspace import Workspace

    workspace_root = tmp_path / "workspace"
    operation = SysOperation(SysOperationCard(
        id="context-reload-test",
        mode=OperationMode.LOCAL,
        work_config=LocalWorkConfig(
            restrict_to_sandbox=True,
            sandbox_root=[str(workspace_root)],
        ),
    ))
    workspace = Workspace(root_path=str(workspace_root), language="cn")
    engine = ContextEngine(
        ContextEngineConfig(enable_reload=True),
        workspace=workspace,
        sys_operation=operation,
    )
    context = await engine.create_context(processors=[(
        "MessageOffloader",
        MessageOffloaderConfig(
            tokens_threshold=1,
            large_message_threshold=10,
            trim_size=3,
            keep_last_round=False,
            protected_tool_names=[],
        ),
    )])
    raw_content = "需要恢复的完整工具结果" * 100
    await context.add_messages(_tool_round("问题", "回答", raw_content))

    offloaded = context.get_messages()[2]
    assert "type=filesystem" in offloaded.content
    offload_path = re.search(r"path=([^]\s]+)", offloaded.content).group(1)
    assert offload_path.startswith(str(workspace_root))
    read_tool = ReadFileTool(operation, enable_image_multimodal=False)
    result = await read_tool.invoke({"file_path": offload_path})
    assert result.success is True
    assert raw_content in result.data["content"]

    state = context.save_state()
    restored = await ContextEngine(
        ContextEngineConfig(enable_reload=True),
        workspace=workspace,
        sys_operation=operation,
    ).create_context()
    restored.load_state({"default_context_id": state})
    restored_path = re.search(
        r"path=([^]\s]+)", restored.get_messages()[2].content,
    ).group(1)
    restored_result = await read_tool.invoke({"file_path": restored_path})
    assert restored_result.success is True
    assert raw_content in restored_result.data["content"]

    outside = tmp_path / "outside.txt"
    outside.write_text("禁止读取", encoding="utf-8")
    denied = await read_tool.invoke({"file_path": str(outside)})
    assert denied.success is False


async def test_react_agent_reloads_offloaded_content_with_native_tool(monkeypatch, tmp_path):
    import json
    import re

    from openjiuwen.core.runner import Runner
    from openjiuwen.core.session.agent import create_agent_session
    from src.agent_v3 import agent_factory
    from src.config import Settings

    Runner.resource_mgr.remove_sys_operation("agent-v3-context-offload")
    agent_factory._agent = None
    settings = Settings(
        _env_file=None,
        LLM_API_KEY="k",
        LLM_BASE_URL="https://x",
        LLM_MODEL="m",
        AGENT_V3_CONTEXT_OFFLOAD_TOKENS_THRESHOLD=1,
        AGENT_V3_CONTEXT_OFFLOAD_LARGE_MESSAGE_THRESHOLD=10,
        AGENT_V3_CONTEXT_OFFLOAD_TRIM_SIZE=3,
        AGENT_V3_CONTEXT_MESSAGES_TO_KEEP=20,
        AGENT_V3_CONTEXT_COMPRESSION_ENABLED=False,
        AGENT_V3_CONTEXT_WINDOW_ROUNDS=0,
        AGENT_V3_CONTEXT_WORKSPACE_DIR=str(tmp_path / "workspace"),
    )
    monkeypatch.setattr(agent_factory, "get_settings", lambda: settings)
    monkeypatch.setattr(agent_factory, "build_system_prompt", lambda: "sys")
    raw_content = "主链路恢复的完整工具结果" * 100
    main_calls = []

    class FakeMainModel:
        async def invoke(self, messages, **kwargs):
            main_calls.append(messages)
            if len(main_calls) == 1:
                marker = next(
                    message.content for message in messages
                    if "[[OFFLOAD:" in getattr(message, "content", "")
                )
                path = re.search(r"path=([^]\s]+)", marker).group(1)
                return AssistantMessage(
                    content="恢复历史结果",
                    tool_calls=[ToolCall(
                        id="reload-call",
                        type="function",
                        name="read_file",
                        arguments=json.dumps({"file_path": path}),
                    )],
                )
            return AssistantMessage(content="历史结果已恢复")

    try:
        agent = await agent_factory.get_v3_agent()
        agent.set_llm(FakeMainModel())
        session = create_agent_session(session_id="reload-main-test", card=agent.card)
        context = await agent._init_context(session)
        await context.add_messages(_tool_round("历史问题", "历史回答", raw_content))

        result = await agent.invoke("请恢复历史工具结果", session=session)

        assert result is not None
        assert len(main_calls) == 2
        tool_results = [
            message for message in main_calls[1]
            if getattr(message, "role", "") == "tool"
        ]
        assert any(raw_content in message.content for message in tool_results)
        assert not any(
            getattr(message, "content", "").startswith("未知工具")
            for message in main_calls[1]
        )
    finally:
        agent_factory._agent = None
        Runner.resource_mgr.remove_sys_operation("agent-v3-context-offload")
