import os
import threading
import webbrowser

import uvicorn

from .app import access_keys, lan_ip

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    # 0.0.0.0 = o celular no mesmo Wi-Fi também consegue abrir (com PIN)
    host = os.environ.get("HOST", "0.0.0.0")
    url = f"http://127.0.0.1:{port}"
    password, _ = access_keys()
    print(f"\n  Edita Fácil rodando!  No computador: {url}")
    if host == "0.0.0.0":
        print(f"  No celular (mesmo Wi-Fi): http://{lan_ip()}:{port}/celular.html   PIN: {password}")
    print("  (Ctrl+C para fechar)\n")
    if not os.environ.get("NO_BROWSER"):
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("server.app:app", host=host, port=port, log_level="warning")
