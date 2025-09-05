#!/usr/bin/env python3
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
import os

# Add current directory to path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from summarizer.chunking import chunk_text
    from summarizer.llm import analyze_chunk, consolidate_task_outputs
    MODULES_OK = True
except Exception as e:
    MODULES_OK = False
    MODULE_ERROR = str(e)

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            response = {"status": "ok", "modules": MODULES_OK}
            if not MODULES_OK:
                response["error"] = MODULE_ERROR
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == '/test-summarize':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode())
                text = data.get('text', '')
                task = data.get('task', 'summary')
                
                if not MODULES_OK:
                    raise Exception(f"Modules not loaded: {MODULE_ERROR}")
                
                # Process the text
                chunks = chunk_text([text], chunk_size=1000, chunk_overlap=100)
                outputs = [analyze_chunk(c, task=task) for c in chunks]
                final = consolidate_task_outputs(outputs, task=task, focus=None)
                
                result = {
                    "success": True,
                    "chunks": len(chunks),
                    "partial": outputs,
                    "final": final
                }
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                error_response = {"success": False, "error": str(e)}
                self.wfile.write(json.dumps(error_response).encode())
        elif self.path == '/summarize-stream':
            # Frontend compatibility endpoint
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode())
                text = data.get('text', '')
                task = data.get('task', 'summary')
                focus = data.get('focus')
                chunk_size = data.get('chunk_size', 3000)
                chunk_overlap = data.get('chunk_overlap', 300)
                
                if not MODULES_OK:
                    raise Exception(f"Modules not loaded: {MODULE_ERROR}")
                
                # Process the text
                chunks = chunk_text([text], chunk_size=chunk_size, chunk_overlap=chunk_overlap)
                outputs = [analyze_chunk(c, task=task) for c in chunks]
                final = consolidate_task_outputs(outputs, task=task, focus=focus)
                
                # Return in expected format for frontend
                result = {
                    "type": "complete",
                    "chunks": len(chunks),
                    "task": task,
                    "partial": outputs,
                    "final": final
                }
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                error_response = {"error": str(e)}
                self.wfile.write(json.dumps(error_response).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

if __name__ == '__main__':
    server = HTTPServer(('127.0.0.1', 8003), RequestHandler)
    print("Basic HTTP server running on http://127.0.0.1:8003")
    print("Test endpoints:")
    print("  GET /health")
    print("  POST /test-summarize")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
