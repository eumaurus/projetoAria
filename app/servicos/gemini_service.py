"""Interface com Gemini, OpenAI ou modo mock."""

from __future__ import annotations

import logging
import json
import re
from urllib import error, request

from app.servicos.base_service import BaseService
from app.servicos.config import Config


class GeminiService(BaseService):
    """Encapsula chamadas ao provedor de LLM configurado."""

    def __init__(self, config: Config, logger: logging.Logger) -> None:
        super().__init__(config, logger)
        self._modelo = None
        self._vertex_inicializado = False
        self._api_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.config.gemini_model}:generateContent"
        )

    def _inicializar_vertex(self) -> None:
        if self._vertex_inicializado:
            return

        if not self.config.google_cloud_project:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT não configurado. Defina no arquivo .env."
            )

        import vertexai
        from vertexai.generative_models import GenerativeModel

        vertexai.init(
            project=self.config.google_cloud_project,
            location=self.config.google_cloud_location,
        )
        self._modelo = GenerativeModel(self.config.gemini_model)
        self._vertex_inicializado = True
        self.logger.info(
            "Vertex AI inicializado: projeto=%s, modelo=%s",
            self.config.google_cloud_project,
            self.config.gemini_model,
        )

    def _gerar_api(self, prompt: str, system_prompt: str = "") -> str:
        if not self.config.google_api_key:
            raise ValueError(
                "GEMINI_API_KEY/GOOGLE_API_KEY não configurada. Defina no ambiente do app."
            )

        partes: list[dict[str, str]] = []
        if system_prompt.strip():
            partes.append({"text": system_prompt.strip()})
        if prompt.strip():
            partes.append({"text": prompt.strip()})

        payload = {
            "contents": [{"role": "user", "parts": partes}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 4096,
            },
        }
        req = request.Request(
            f"{self._api_url}?key={self.config.google_api_key}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=120) as resposta:
                dados = json.loads(resposta.read().decode("utf-8"))
        except error.HTTPError as exc:
            corpo = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Erro Gemini API ({exc.code}): {corpo}") from exc

        candidatos = dados.get("candidates") or []
        if not candidatos:
            raise RuntimeError(f"Resposta vazia da Gemini API: {dados}")

        partes_resposta = candidatos[0].get("content", {}).get("parts", [])
        texto = "".join(parte.get("text", "") for parte in partes_resposta if isinstance(parte, dict))
        return texto.strip()

    def _gerar_openai(self, prompt: str, system_prompt: str = "") -> str:
        if not self.config.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY não configurada. Defina no ambiente do app."
            )

        mensagens: list[dict[str, str]] = []
        if system_prompt.strip():
            mensagens.append({"role": "system", "content": system_prompt.strip()})
        mensagens.append({"role": "user", "content": prompt.strip()})

        payload = {
            "model": self.config.openai_model,
            "messages": mensagens,
            "temperature": 0.2,
        }
        req = request.Request(
            f"{self.config.openai_base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.openai_api_key}",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=120) as resposta:
                dados = json.loads(resposta.read().decode("utf-8"))
        except error.HTTPError as exc:
            corpo = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Erro OpenAI API ({exc.code}): {corpo}") from exc

        escolhas = dados.get("choices") or []
        if not escolhas:
            raise RuntimeError(f"Resposta vazia da OpenAI API: {dados}")

        mensagem = escolhas[0].get("message", {})
        conteudo = mensagem.get("content", "")
        if isinstance(conteudo, list):
            texto = "".join(
                parte.get("text", "")
                for parte in conteudo
                if isinstance(parte, dict)
            )
            return texto.strip()
        return str(conteudo).strip()

    def gerar(self, prompt: str, system_prompt: str = "") -> str:
        """Gera texto a partir de prompt e instrução de sistema."""
        if self.config.llm_provider == "openai":
            return self._gerar_openai(prompt, system_prompt)

        if self.config.gemini_modo == "api":
            return self._gerar_api(prompt, system_prompt)

        self._inicializar_vertex()

        from vertexai.generative_models import GenerationConfig

        conteudo = prompt
        if system_prompt:
            conteudo = f"{system_prompt.strip()}\n\n---\n\n{prompt.strip()}"

        resposta = self._modelo.generate_content(
            conteudo,
            generation_config=GenerationConfig(
                temperature=0.2,
                max_output_tokens=4096,
            ),
        )

        texto = getattr(resposta, "text", "") or ""
        if not texto and resposta.candidates:
            partes = resposta.candidates[0].content.parts
            texto = "".join(getattr(p, "text", "") for p in partes)

        return texto.strip()

    def gerar_sql(self, prompt: str, system_prompt: str = "") -> str:
        """Gera SQL e extrai apenas o bloco executável."""
        texto = self.gerar(prompt, system_prompt)
        return self._extrair_sql(texto)

    @staticmethod
    def _extrair_sql(texto: str) -> str:
        match = re.search(r"```sql\s*(.*?)\s*```", texto, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()

        match = re.search(r"(SELECT\s.+)", texto, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip().rstrip(";")

        return texto.strip()


def criar_gemini_service(config: Config, logger: logging.Logger):
    """Factory que escolhe implementação real ou mock conforme configuração."""
    from app.servicos.gemini_mock_service import GeminiMockService

    if config.llm_provider == "mock" or config.gemini_modo == "mock":
        return GeminiMockService(config, logger)
    return GeminiService(config, logger)

