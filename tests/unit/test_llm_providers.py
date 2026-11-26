"""LLM provider layer: factory, selection, configuration and the four providers.

Cloud providers are tested with their vendor SDK replaced by a fake, so nothing leaves the
machine. One test per cloud provider also builds the real vendor class (no request is sent)
to prove the parameter names we pass are the ones the SDK accepts.
"""

import sys
from types import ModuleType
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_ollama import ChatOllama
from pydantic import Field

from app.config import Settings
from app.providers.llm import (
    LLMProvider,
    LLMProviderError,
    ModelInfo,
    available_providers,
    create_llm_provider,
    register_provider,
)
from app.providers.llm import factory as factory_module
from tests.conftest import FakeProvider, fake_llm, make_settings

CLOUD = [
    # name, vendor module, vendor class, settings field for the key, env var
    ("openai", "langchain_openai", "ChatOpenAI", "openai_api_key", "OPENAI_API_KEY"),
    ("gemini", "langchain_google_genai", "ChatGoogleGenerativeAI", "google_api_key", "GOOGLE_API_KEY"),
    ("groq", "langchain_groq", "ChatGroq", "groq_api_key", "GROQ_API_KEY"),
]
CLOUD_IDS = [c[0] for c in CLOUD]


class FakeVendorChat(GenericFakeChatModel):
    """Stands in for a vendor chat class and records the keyword arguments it was built with."""

    init_kwargs: dict[str, Any] = Field(default_factory=dict)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(messages=iter([AIMessage(content="cloud reply")]), init_kwargs=kwargs)


def mock_vendor(monkeypatch: pytest.MonkeyPatch, module: str, cls: str) -> None:
    fake_module = ModuleType(module)
    setattr(fake_module, cls, FakeVendorChat)
    monkeypatch.setitem(sys.modules, module, fake_module)


# -- Factory and selection ------------------------------------------------------------------


def test_available_providers() -> None:
    assert available_providers() == ["gemini", "groq", "ollama", "openai"]


@pytest.mark.parametrize(
    ("name", "class_name"),
    [
        ("ollama", "OllamaProvider"),
        ("openai", "OpenAIProvider"),
        ("gemini", "GeminiProvider"),
        ("groq", "GroqProvider"),
    ],
)
def test_factory_selects_provider_from_settings(name: str, class_name: str) -> None:
    # Creating any provider needs no API key and no network.
    provider = create_llm_provider(make_settings(llm_provider=name))
    assert isinstance(provider, LLMProvider)
    assert type(provider).__name__ == class_name
    assert provider.name == name


def test_factory_reads_llm_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    assert create_llm_provider().name == "groq"


def test_factory_rejects_unknown_provider() -> None:
    settings = Settings.model_construct(llm_provider="unknown")
    with pytest.raises(LLMProviderError, match="Unknown LLM provider 'unknown'"):
        create_llm_provider(settings)


def test_register_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(factory_module, "_REGISTRY", dict(factory_module._REGISTRY))
    register_provider("custom", "tests.unit.test_llm_providers:CustomProvider")

    provider = create_llm_provider(
        Settings.model_construct(**{**make_settings().model_dump(), "llm_provider": "custom"})
    )
    assert isinstance(provider, CustomProvider)
    assert "custom" in available_providers()


def test_register_provider_rejects_bad_target() -> None:
    with pytest.raises(ValueError, match="module:Class"):
        register_provider("bad", "no_colon_here")


def test_factory_rejects_non_provider_class(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(factory_module, "_REGISTRY", {"ollama": "app.config:Settings"})
    with pytest.raises(LLMProviderError, match="not an LLMProvider"):
        create_llm_provider(make_settings())


class CustomProvider(FakeProvider):
    def __init__(self, settings: Settings) -> None:
        super().__init__(fake_llm("custom"), settings)


# -- Configuration resolution (shared by every provider) ------------------------------------


def test_model_info_uses_provider_settings() -> None:
    provider = create_llm_provider(make_settings(ollama_model="phi3:latest", llm_timeout=30))
    assert provider.model_info == ModelInfo(
        provider="ollama", model="phi3:latest", temperature=0.0, timeout=30
    )


def test_provider_temperature_overrides_global() -> None:
    settings = make_settings(llm_temperature=0.3, ollama_temperature=0.9)
    assert create_llm_provider(settings).model_info.temperature == 0.9


def test_global_temperature_used_when_provider_has_none() -> None:
    settings = make_settings(llm_provider="groq", llm_temperature=0.4)
    assert create_llm_provider(settings).model_info.temperature == 0.4


def test_call_overrides_win() -> None:
    provider = create_llm_provider(make_settings(ollama_temperature=0.9))
    model = provider.chat_model(model="mistral:7b", temperature=0.1)
    assert isinstance(model, ChatOllama)
    assert (model.model, model.temperature) == ("mistral:7b", 0.1)


# -- Ollama ---------------------------------------------------------------------------------


def test_ollama_initialization() -> None:
    settings = make_settings(
        ollama_base_url="http://ollama:11434",
        ollama_model="phi3:latest",
        ollama_temperature=0.2,
        llm_timeout=45,
    )
    model = create_llm_provider(settings).chat_model()

    assert isinstance(model, ChatOllama)
    assert model.base_url == "http://ollama:11434"
    assert model.model == "phi3:latest"
    assert model.temperature == 0.2
    assert model.client_kwargs == {"timeout": 45}


def test_default_chat_model_is_cached() -> None:
    provider = create_llm_provider(make_settings())
    assert provider.chat_model() is provider.chat_model()
    assert provider.chat_model(model="other") is not provider.chat_model()


# -- Cloud providers (mocked) ---------------------------------------------------------------


@pytest.mark.parametrize(("name", "module", "cls", "key_field", "env_var"), CLOUD, ids=CLOUD_IDS)
def test_cloud_provider_does_not_need_key_until_used(
    name: str, module: str, cls: str, key_field: str, env_var: str
) -> None:
    provider = create_llm_provider(make_settings(llm_provider=name))
    assert provider.model_info.provider == name  # usable for inspection without a key

    with pytest.raises(LLMProviderError, match=env_var):
        provider.chat_model()


@pytest.mark.parametrize(("name", "module", "cls", "key_field", "env_var"), CLOUD, ids=CLOUD_IDS)
def test_cloud_provider_passes_configuration(
    monkeypatch: pytest.MonkeyPatch, name: str, module: str, cls: str, key_field: str, env_var: str
) -> None:
    mock_vendor(monkeypatch, module, cls)
    settings = make_settings(
        llm_provider=name,
        llm_temperature=0.5,
        llm_timeout=20,
        **{key_field: "secret-key", f"{name}_model": "m-1"},
    )

    model = create_llm_provider(settings).chat_model()

    assert isinstance(model, FakeVendorChat)
    kwargs = model.init_kwargs
    key = kwargs.get("api_key") or kwargs.get("google_api_key")
    assert key.get_secret_value() == "secret-key"
    assert (kwargs["model"], kwargs["temperature"], kwargs["timeout"]) == ("m-1", 0.5, 20)


@pytest.mark.parametrize(("name", "module", "cls", "key_field", "env_var"), CLOUD, ids=CLOUD_IDS)
def test_cloud_provider_invoke_and_stream(
    monkeypatch: pytest.MonkeyPatch, name: str, module: str, cls: str, key_field: str, env_var: str
) -> None:
    mock_vendor(monkeypatch, module, cls)
    settings = make_settings(llm_provider=name, **{key_field: "k"})

    reply = create_llm_provider(settings).invoke([HumanMessage(content="hi")])
    assert isinstance(reply, AIMessage)
    assert reply.content == "cloud reply"

    chunks = list(create_llm_provider(settings).stream([HumanMessage(content="hi")]))
    assert "".join(c.text for c in chunks) == "cloud reply"


@pytest.mark.parametrize(("name", "module", "cls", "key_field", "env_var"), CLOUD, ids=CLOUD_IDS)
def test_cloud_provider_builds_real_vendor_class(
    name: str, module: str, cls: str, key_field: str, env_var: str
) -> None:
    settings = make_settings(llm_provider=name, llm_timeout=12, **{key_field: "k", f"{name}_model": "m-1"})
    model = create_llm_provider(settings).chat_model()

    assert type(model).__name__ == cls
    assert getattr(model, "model_name", None) == "m-1" or getattr(model, "model", None) in (
        "m-1",
        "models/m-1",
    )
    assert getattr(model, "request_timeout", None) == 12 or getattr(model, "timeout", None) == 12


def test_missing_extra_gives_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "langchain_groq", None)  # makes the import fail
    provider = create_llm_provider(make_settings(llm_provider="groq", groq_api_key="k"))
    with pytest.raises(LLMProviderError, match="uv sync --extra groq"):
        provider.chat_model()


# -- Invocation through the base class ------------------------------------------------------


def test_invoke_and_stream_delegate_to_chat_model() -> None:
    assert FakeProvider(fake_llm("hello there")).invoke([HumanMessage(content="hi")]).content == "hello there"
    chunks = list(FakeProvider(fake_llm("hello there")).stream([HumanMessage(content="hi")]))
    assert [c.text for c in chunks] == ["hello", " ", "there"]


async def test_async_invoke_and_stream() -> None:
    assert (await FakeProvider(fake_llm("async")).ainvoke([HumanMessage(content="hi")])).content == "async"
    chunks = [c.text async for c in FakeProvider(fake_llm("a b")).astream([HumanMessage(content="hi")])]
    assert "".join(chunks) == "a b"


def test_invoke_rejects_non_ai_message() -> None:
    class WrongModel(GenericFakeChatModel):
        def invoke(self, *args: Any, **kwargs: Any) -> Any:
            return HumanMessage(content="not an AI message")

    with pytest.raises(LLMProviderError, match="expected AIMessage"):
        FakeProvider(WrongModel(messages=iter([]))).invoke([HumanMessage(content="hi")])
