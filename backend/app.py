from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import os
import json
from dotenv import load_dotenv
from rag import RAGPipeline

load_dotenv()

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

rag = RAGPipeline()


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {".pdf", ".txt"}:
        return jsonify({"error": "Only PDF and TXT files are supported"}), 400
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)
    try:
        chunk_count, questions = rag.ingest(filepath)
        return jsonify({
            "message": f"Successfully ingested '{file.filename}'",
            "chunks": chunk_count,
            "filename": file.filename,
            "suggested_questions": questions
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/query", methods=["POST"])
def query():
    data = request.get_json()
    if not data or "question" not in data:
        return jsonify({"error": "No question provided"}), 400
    question = data["question"].strip()
    if not question:
        return jsonify({"error": "Question cannot be empty"}), 400

    def generate():
        try:
            sources = []
            for chunk in rag.query_stream(question):
                if isinstance(chunk, dict) and "sources" in chunk:
                    sources = chunk["sources"]
                else:
                    yield f"data: {json.dumps({'token': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True, 'sources': sources})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/summarize/<path:filename>", methods=["POST"])
def summarize(filename):
    def generate():
        try:
            for chunk in rag.summarize_stream(filename):
                yield f"data: {json.dumps({'token': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/documents", methods=["GET"])
def documents():
    docs = rag.get_documents()
    return jsonify({"session": docs["session"], "history": docs["history"], "active": rag.active_docs})


@app.route("/history/activate/<path:filename>", methods=["POST"])
def activate_history(filename):
    try:
        rag.activate_from_history(filename)
        return jsonify({"message": f"Activated '{filename}'", "active": rag.active_docs})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/documents/active", methods=["POST"])
def set_active():
    data = request.get_json()
    rag.set_active_docs(data.get("docs", []))
    return jsonify({"active": rag.active_docs})


@app.route("/documents/<path:filename>", methods=["DELETE"])
def remove_doc(filename):
    rag.remove_document(filename)
    return jsonify({"message": f"Removed '{filename}'"})


@app.route("/history/clear", methods=["POST"])
def clear_history():
    rag.clear_history()
    return jsonify({"message": "Conversation history cleared"})


@app.route("/clear", methods=["POST"])
def clear():
    rag.clear()
    return jsonify({"message": "All documents cleared"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)