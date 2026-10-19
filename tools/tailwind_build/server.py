import http.server,json,os
D=os.path.dirname(__file__)
class H(http.server.BaseHTTPRequestHandler):
    def _c(self):
        self.send_header('Access-Control-Allow-Origin','*')
    def do_GET(self):
        p='tokens.json' if self.path.startswith('/tokens') else 'harness.html'
        b=open(os.path.join(D,p),'rb').read()
        self.send_response(200);self.send_header('Content-Type','text/html' if p.endswith('html') else 'application/json');self._c();self.end_headers();self.wfile.write(b)
    def do_POST(self):
        n=int(self.headers['Content-Length']);b=self.rfile.read(n)
        open(os.path.join(D,'out.css'),'wb').write(b)
        self.send_response(200);self._c();self.end_headers();self.wfile.write(b'ok')
    def do_OPTIONS(self):
        self.send_response(204);self._c();self.send_header('Access-Control-Allow-Headers','*');self.end_headers()
    def log_message(self,*a):pass
http.server.HTTPServer(('127.0.0.1',5056),H).serve_forever()
