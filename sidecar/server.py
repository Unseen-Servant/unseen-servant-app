"""
Unseen Servant — ChromaDB indexing sidecar.

Started automatically by the Tauri desktop app.
Provides HTTP endpoints for indexing PDFs and searching indexed content.

Usage:
    python server.py --port 8420 --data-dir /path/to/app/data
"""

import argparse
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from pypdf import PdfReader
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn


# ---------------------------------------------------------------------------
# CLI arguments
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Unseen Servant indexing sidecar")
    parser.add_argument("--port", type=int, default=8420, help="HTTP port")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="Directory for ChromaDB storage (default: ./chroma_db)")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Pure helpers (no dependencies — safe to import in tests)
# ---------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks.

    Why overlapping? If a sentence spans two chunks, the overlap ensures
    it appears fully in at least one chunk, improving search quality.
    """
    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunk = text[i:i + chunk_size]
        if chunk.strip():
            chunks.append(chunk)
    return chunks


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class IndexFilesRequest(BaseModel):
    paths: list[str]

class SearchRequest(BaseModel):
    query: str
    n_results: int = 5
    source_filter: str | None = None


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(collection=None):
    """Create the FastAPI app, optionally with a pre-configured collection.

    In production: called with no arguments — sets up Ollama + PersistentClient.
    In tests: called with a test collection (EphemeralClient + ONNX embeddings).

    This pattern is called "dependency injection." The endpoints don't care
    HOW the collection was created — they just use it. This lets tests swap
    in a lightweight in-memory collection without needing Ollama running.
    """
    if collection is None:
        # Production path: same setup as before, but now only runs
        # when the server is actually started (not at import time).
        args = parse_args()
        data_dir = Path(args.data_dir) if args.data_dir else Path(__file__).parent / "chroma_db"
        data_dir.mkdir(parents=True, exist_ok=True)

        chroma_client = chromadb.PersistentClient(path=str(data_dir))
        ollama_ef = embedding_functions.OllamaEmbeddingFunction(
            url="http://localhost:11434/api/embeddings",
            model_name="nomic-embed-text"
        )
        collection = chroma_client.get_or_create_collection(
            name="ttrpg_docs",
            embedding_function=ollama_ef
        )

    app = FastAPI(title="Unseen Servant Sidecar")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Endpoints (close over `collection` from the factory)
    # ------------------------------------------------------------------

    @app.get("/health")
    async def health():
        """Health check for startup detection."""
        return {"status": "ok"}

    @app.post("/api/index-files")
    async def index_files(request: IndexFilesRequest):
        """Index specific PDF files by path."""
        total = len(request.paths)
        indexed = 0
        errors = []

        for pdf_path_str in request.paths:
            pdf_path = Path(pdf_path_str)

            if not pdf_path.exists():
                errors.append(f"{pdf_path.name}: File not found")
                continue

            try:
                reader = PdfReader(pdf_path)
                text = ""
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text

                if not text.strip():
                    errors.append(f"{pdf_path.name}: Empty or scanned PDF")
                    continue

                chunks = chunk_text(text)

                # Store in ChromaDB in batches of 100
                batch_size = 100
                for batch_idx in range(0, len(chunks), batch_size):
                    batch_chunks = chunks[batch_idx:batch_idx + batch_size]
                    batch_metadatas = [{
                        "source": str(pdf_path),
                        "filename": pdf_path.name,
                        "chunk": batch_idx + chunk_idx
                    } for chunk_idx in range(len(batch_chunks))]
                    batch_ids = [
                        f"{pdf_path.stem}_{batch_idx + chunk_idx}"
                        for chunk_idx in range(len(batch_chunks))
                    ]

                    collection.upsert(
                        documents=batch_chunks,
                        metadatas=batch_metadatas,
                        ids=batch_ids
                    )

                indexed += 1

            except Exception as e:
                errors.append(f"{pdf_path.name}: {str(e)}")

        return {
            "indexed": indexed,
            "total": total,
            "errors": errors
        }

    @app.get("/api/stats")
    async def get_stats():
        """Database statistics."""
        try:
            count = collection.count()
            results = collection.get(include=["metadatas"])
            unique_sources = (
                len(set(m.get("filename") for m in results["metadatas"]))
                if results["metadatas"] else 0
            )
            return {
                "total_chunks": count,
                "total_documents": unique_sources,
                "collection_name": collection.name
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/sources")
    async def get_sources():
        """List all indexed PDFs with chunk counts."""
        try:
            results = collection.get(include=["metadatas"])
            if not results["metadatas"]:
                return {"sources": [], "count": 0}

            sources_info = {}
            for metadata in results["metadatas"]:
                filename = metadata["filename"]
                if filename not in sources_info:
                    sources_info[filename] = {
                        "filename": filename,
                        "source": metadata.get("source", ""),
                        "chunks": 0
                    }
                sources_info[filename]["chunks"] += 1

            sources_list = sorted(sources_info.values(), key=lambda x: x["filename"])
            return {"sources": sources_list, "count": len(sources_list)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/api/source/{filename}")
    async def delete_source(filename: str):
        """Delete a source and all its chunks."""
        try:
            results = collection.get(include=["metadatas"])
            ids_to_delete = [
                id for id, metadata in zip(results["ids"], results["metadatas"])
                if metadata.get("filename") == filename
            ]

            if not ids_to_delete:
                raise HTTPException(status_code=404, detail=f"Source not found: {filename}")

            collection.delete(ids=ids_to_delete)
            return {"message": f"Deleted {len(ids_to_delete)} chunks from {filename}"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/source/{filename}/content")
    async def get_source_content(filename: str):
        """Retrieve the full text content of an indexed PDF.

        Fetches all chunks for the given filename from ChromaDB,
        sorts them by chunk index, and concatenates them into
        one continuous text.
        """
        try:
            results = collection.get(
                where={"filename": filename},
                include=["documents", "metadatas"],
            )

            if not results["ids"]:
                raise HTTPException(
                    status_code=404, detail=f"Source not found: {filename}"
                )

            # Sort chunks by their index so the text reads in order
            paired = sorted(
                zip(results["documents"], results["metadatas"]),
                key=lambda pair: pair[1].get("chunk", 0),
            )
            content = "\n".join(doc for doc, _ in paired)

            return {
                "filename": filename,
                "chunks": len(paired),
                "content": content,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/search")
    async def search(request: SearchRequest):
        """Semantic search across indexed documents."""
        try:
            query_kwargs = {
                "query_texts": [request.query],
                "n_results": request.n_results,
            }
            if request.source_filter:
                query_kwargs["where"] = {"filename": request.source_filter}

            results = collection.query(**query_kwargs)

            if not results["documents"][0]:
                return {"results": [], "message": "No results found."}

            formatted = []
            for doc, metadata, distance in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0]
            ):
                formatted.append({
                    "text": doc,
                    "filename": metadata["filename"],
                    "source": metadata.get("source", ""),
                    "chunk": metadata.get("chunk", 0),
                    "relevance": round(1 - distance, 3)
                })

            return {"results": formatted}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return app


# ---------------------------------------------------------------------------
# Main (only runs when executed directly, NOT when imported by tests)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = parse_args()
    data_dir = Path(args.data_dir) if args.data_dir else Path(__file__).parent / "chroma_db"
    print(f"Starting sidecar on port {args.port}, data dir: {data_dir}")
    application = create_app()
    uvicorn.run(application, host="127.0.0.1", port=args.port, log_level="info")
