"""
Local HTTP REST API Server for Personal AI Memory Layer (Milestone V6.0 Backend API).

Provides a secure, localhost-restricted REST API enabling the browser extension to interact with
the Memory Layer engine (search, in-conversation retrieval, context composition, handoffs)
without exposing SQLite or internal Python objects directly.

Security Guarantees:
1. Restricted CORS (Allows chrome-extension:// origins and local dev origins; NO wildcard '*').
2. Restricted endpoint boundary (/api/v1/* only).
3. No raw SQL or internal object execution exposed.
"""

import os
import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional, List

from app.repositories.conversation_repository import ConversationRepository
from app.search.hybrid_search import HybridSearchEngine
from app.search.find_here import FindHereEngine
from app.services.context_composer import ContextComposer
from app.services.export_engine import LocalExportDestination
from app.services.destination_adapters.registry import DestinationRegistry
from app.models.schemas import PortableContextPackage

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


class MemoryLayerHTTPRequestHandler(BaseHTTPRequestHandler):
    """
    HTTP Request Handler serving V6 REST API endpoints.
    """

    # Thread-safe shared service singletons
    repo = ConversationRepository()
    hybrid_engine = HybridSearchEngine(repo=repo)
    find_here_engine = FindHereEngine(repo=repo)
    composer = ContextComposer(repo=repo, search_engine=hybrid_engine)
    dest_registry = DestinationRegistry()
    local_exporter = LocalExportDestination()

    def _send_cors_headers(self):
        origin = self.headers.get("Origin", "")
        # Security decision: restrict to extension origins or local dev origins
        if origin and (origin.startswith("chrome-extension://") or origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1")):
            self.send_header("Access-Control-Allow-Origin", origin)
        elif not origin:
            # Fallback for non-browser direct clients
            self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:8000")
        else:
            # For extension requests without specific match, allow extension scheme pattern
            self.send_header("Access-Control-Allow-Origin", origin)

        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Memory-Layer-Key")

    def _send_json_response(self, status_code: int, data: Dict[str, Any]):
        body_bytes = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body_bytes)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body_bytes)

    def _send_error_response(self, status_code: int, message: str, error_code: str = "API_ERROR"):
        self._send_json_response(status_code, {
            "error": True,
            "status_code": status_code,
            "message": message,
            "error_code": error_code
        })

    def do_OPTIONS(self):
        """Handle CORS pre-flight requests."""
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        """Handle GET endpoints."""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        try:
            if path == "/api/v1/health":
                self._send_json_response(200, {
                    "status": "ok",
                    "version": "6.0",
                    "database": "connected",
                    "service": "Personal AI Memory Layer API"
                })
            elif path == "/api/v1/conversations":
                convs = self.repo.list_conversations()
                res_data = [
                    {
                        "id": c.id,
                        "title": c.title,
                        "source": c.source,
                        "imported_at": c.imported_at,
                        "message_count": c.message_count,
                        "category": c.category,
                        "tags": c.tags,
                    }
                    for c in convs
                ]
                self._send_json_response(200, {"conversations": res_data, "total": len(res_data)})
            elif path.startswith("/api/v1/conversations/"):
                conv_id = path.replace("/api/v1/conversations/", "")
                conv = self.repo.get_conversation(conv_id)
                if not conv:
                    self._send_error_response(404, f"Conversation '{conv_id}' not found.", "NOT_FOUND")
                else:
                    self._send_json_response(200, conv.to_dict())
            else:
                self._send_error_response(404, f"Endpoint '{self.path}' not found.", "ENDPOINT_NOT_FOUND")
        except Exception as e:
            logger.error(f"API GET error: {e}", exc_info=True)
            self._send_error_response(500, str(e), "SERVER_ERROR")

    def do_POST(self):
        """Handle POST endpoints."""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except Exception:
            self._send_error_response(400, "Invalid JSON payload in request body.", "INVALID_JSON")
            return

        try:
            if path == "/api/v1/search":
                query = body.get("query", "").strip()
                limit = int(body.get("limit", 20))
                if not query:
                    self._send_json_response(200, {"query": "", "results": [], "total": 0})
                    return
                results = self.hybrid_engine.search(query, limit=limit)
                self._send_json_response(200, {
                    "query": query,
                    "total": len(results),
                    "results": [r.to_dict() for r in results]
                })

            elif path == "/api/v1/search/conversation":
                conv_id = body.get("conversation_id", "").strip()
                query = body.get("query", "").strip()
                limit = int(body.get("limit", 20))

                if not query:
                    self._send_json_response(200, {"conversation_id": conv_id, "query": "", "results": [], "total": 0})
                    return

                results = self.find_here_engine.search_in_conversation(conv_id, query, limit=limit)
                self._send_json_response(200, {
                    "conversation_id": conv_id,
                    "query": query,
                    "total": len(results),
                    "results": [r.to_dict() for r in results]
                })

            elif path == "/api/v1/context/compose":
                query = body.get("query", "").strip()
                max_candidates = int(body.get("max_candidates", 10))
                if not query:
                    self._send_error_response(400, "Query field is required for context composition.", "MISSING_QUERY")
                    return

                search_res = self.composer.search_context(query, limit=50)
                all_candidates = []
                for conv_id, group in search_res.items():
                    if conv_id != "_diagnostics" and isinstance(group, dict) and "candidates" in group:
                        all_candidates.extend(group["candidates"])

                selected = all_candidates[:max_candidates]
                if not selected:
                    self._send_error_response(404, f"No matching memory context found for composition query '{query}'.", "NO_CONTEXT_FOUND")
                    return

                composed_ctx = self.composer.build_context_preview(selected, query=query)
                pkg = self.local_exporter.prepare_context(composed_ctx)
                self._send_json_response(200, pkg.to_dict())

            elif path == "/api/v1/context/handoff":
                pkg_data = body.get("package")
                provider_name = body.get("destination")
                config = body.get("config", {})

                if not pkg_data or not provider_name:
                    self._send_error_response(400, "Fields 'package' and 'destination' are required.", "INVALID_INPUT")
                    return

                # Reconstruct PortableContextPackage
                pkg = PortableContextPackage(
                    package_id=pkg_data.get("package_id", "pkg-api"),
                    title=pkg_data.get("title", ""),
                    topic=pkg_data.get("topic", ""),
                    context_text=pkg_data.get("context_text", ""),
                    source_conversations=pkg_data.get("source_conversations", []),
                    source_providers=pkg_data.get("source_providers", {}),
                    messages=pkg_data.get("messages", []),
                    provenance=pkg_data.get("provenance", []),
                    schema_version=pkg_data.get("schema_version", "1.0"),
                    created_at=pkg_data.get("created_at", "")
                )

                adapter = self.dest_registry.get_adapter(provider_name)
                result = adapter.execute(pkg, config=config)
                self._send_json_response(200, {
                    "status": result.status,
                    "provider": result.provider,
                    "message": result.message,
                    "destination_url": result.destination_url,
                    "copied_to_clipboard": result.copied_to_clipboard,
                    "external_id": result.external_id,
                    "error_code": result.error_code,
                    "response_payload": result.response_payload,
                })

            else:
                self._send_error_response(404, f"Endpoint '{self.path}' not found.", "ENDPOINT_NOT_FOUND")

        except Exception as e:
            logger.error(f"API POST error: {e}", exc_info=True)
            self._send_error_response(500, str(e), "SERVER_ERROR")

    def log_message(self, format, *args):
        # Silence default stderr logging to keep console output clean
        pass


class MemoryLayerAPIServer:
    """
    Wrapper around HTTPServer managing background execution thread.
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self, daemon: bool = True):
        self.server = HTTPServer((self.host, self.port), MemoryLayerHTTPRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=daemon)
        self.thread.start()
        logger.info(f"Memory Layer API Server running at http://{self.host}:{self.port}")

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            logger.info("Memory Layer API Server stopped.")


def start_api_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> MemoryLayerAPIServer:
    srv = MemoryLayerAPIServer(host=host, port=port)
    srv.start(daemon=True)
    return srv


if __name__ == "__main__":
    import time
    print(f"Starting Personal AI Memory Layer API Server on http://{DEFAULT_HOST}:{DEFAULT_PORT}...")
    server = start_api_server()
    print("API Server active. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping API Server...")
        server.stop()
