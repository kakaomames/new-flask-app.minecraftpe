import subprocess
import os
import shutil
import time
from flask import Flask, render_template_string, redirect, url_for, flash
import psutil

# --- 設定 ---
# サーバーファイルのテンプレートがあるディレクトリ
SERVER_TEMPLATE_DIR = r"C:\Users\username\MinecraftServer_Template"
# サーバーを格納するルートディレクトリ
SERVERS_ROOT_DIR = r"C:\Users\username\MinecraftServers"
# Javaサーバーのコマンド
SERVER_COMMAND = ["java", "-Xmx2G", "-Xms2G", "-jar", "paper.jar", "nogui"]

# GeyserMCとFloodgateのJARファイルのパス
# これらのファイルをダウンロードして、パスを正確に指定してください
GEYSER_JAR_PATH = r"C:\path\to\Geyser-Spigot.jar"
FLOODGATE_JAR_PATH = r"C:\path\to\Floodgate-Spigot.jar"

# Flaskアプリケーションのインスタンスを作成
app = Flask(__name__)
app.secret_key = b'_5#y2L"F4Q8z\n\xec]/'

# 起動中のサーバープロセスをポート番号をキーとする辞書で管理
running_servers = {}

# --- HTMLテンプレート ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Minecraft Server Manager</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; margin-top: 50px; }
        .button {
            padding: 10px 20px;
            font-size: 16px;
            cursor: pointer;
            border-radius: 5px;
            border: none;
            color: white;
            margin: 10px;
        }
        .start { background-color: #4CAF50; }
        .stop { background-color: #f44336; }
        .server-list {
            margin: 20px auto;
            width: 80%;
            border-collapse: collapse;
        }
        .server-list th, .server-list td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }
        .server-list th {
            background-color: #f2f2f2;
        }
        .flash { padding: 10px; margin: 10px 0; border-radius: 5px; }
        .info { background-color: #2196F3; color: white; }
    </style>
</head>
<body>
    <h1>Minecraft Server Manager</h1>
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        <div class="flash info">
        {% for category, message in messages %}
          {{ message }}
        {% endfor %}
        </div>
      {% endif %}
    {% endwith %}

    <form method="post" action="{{ url_for('start_new_server') }}">
        <button type="submit" class="button start">新しいサーバーを起動</button>
    </form>
    
    <h2>起動中のサーバー一覧</h2>
    {% if servers %}
        <table class="server-list">
            <thead>
                <tr>
                    <th>サーバーディレクトリ</th>
                    <th>Java版ポート</th>
                    <th>統合版ポート</th>
                    <th>Java版接続アドレス</th>
                    <th>統合版接続アドレス</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody>
                {% for port, server_info in servers.items() %}
                <tr>
                    <td>{{ server_info.get('dir') }}</td>
                    <td>{{ port }}</td>
                    <td>{{ server_info.get('bedrock_port') }}</td>
                    <td>127.0.0.1:{{ port }}</td>
                    <td>127.0.0.1:{{ server_info.get('bedrock_port') }}</td>
                    <td>
                        <form method="post" action="{{ url_for('stop_server', port=port) }}" style="display:inline;">
                            <button type="submit" class="button stop">停止</button>
                        </form>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    {% else %}
        <p>現在、起動中のサーバーはありません。</p>
    {% endif %}
</body>
</html>
"""

# --- ユーティリティ関数 ---

def is_port_in_use(port):
    """指定されたポートが使用中かチェックする"""
    for conn in psutil.net_connections():
        if conn.laddr.port == port:
            return True
    return False

def find_available_port(start_port=25565):
    """利用可能なポートを探す"""
    port = start_port
    while is_port_in_use(port):
        port += 1
    return port

def create_server_directory(java_port, bedrock_port):
    """新しいサーバーディレクトリを作成し、テンプレートをコピーする"""
    new_server_dir_name = f"server_{java_port}"
    new_server_dir_path = os.path.join(SERVERS_ROOT_DIR, new_server_dir_name)
    
    # テンプレートディレクトリが存在しない場合は作成
    if not os.path.exists(SERVER_TEMPLATE_DIR):
        os.makedirs(SERVER_TEMPLATE_DIR)
        flash(f"エラー: テンプレートディレクトリ '{SERVER_TEMPLATE_DIR}' が見つかりません。必要なファイルを配置してください。", "info")
        raise FileNotFoundError(f"Template directory not found: {SERVER_TEMPLATE_DIR}")

    shutil.copytree(SERVER_TEMPLATE_DIR, new_server_dir_path)

    # プラグインディレクトリを作成
    plugins_dir = os.path.join(new_server_dir_path, "plugins")
    if not os.path.exists(plugins_dir):
        os.makedirs(plugins_dir)
        
    # プラグインファイルをコピー
    shutil.copy(GEYSER_JAR_PATH, plugins_dir)
    shutil.copy(FLOODGATE_JAR_PATH, plugins_dir)
    
    return new_server_dir_path, new_server_dir_name

def update_server_properties(server_dir, port):
    """server.propertiesのポート番号を更新する"""
    properties_path = os.path.join(server_dir, 'server.properties')
    with open(properties_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    with open(properties_path, 'w', encoding='utf-8') as f:
        for line in lines:
            if line.strip().startswith('server-port='):
                f.write(f'server-port={port}\n')
            else:
                f.write(line)

# --- Flaskルート ---

@app.route("/")
def index():
    """トップページを表示するルート"""
    cleanup_servers()
    return render_template_string(HTML_TEMPLATE, servers=running_servers)

@app.route("/start", methods=["POST"])
def start_new_server():
    """新しいサーバーを起動するルート"""
    try:
        new_java_port = find_available_port(25565)
        new_bedrock_port = find_available_port(19132)
        
        new_server_dir, new_dir_name = create_server_directory(new_java_port, new_bedrock_port)
        update_server_properties(new_server_dir, new_java_port)
        
        server_process = subprocess.Popen(
            SERVER_COMMAND,
            cwd=new_server_dir,
            stdin=subprocess.PIPE,
            text=True
        )
        
        running_servers[new_java_port] = {
            'process': server_process,
            'dir': new_dir_name,
            'path': new_server_dir,
            'bedrock_port': new_bedrock_port
        }
        
        flash(f"ポート {new_java_port} (Java版) と {new_bedrock_port} (統合版) で新しいサーバーを起動しました。", "info")
        
        time.sleep(10)
        
        geyser_config_path = os.path.join(new_server_dir, 'plugins', 'Geyser-Spigot', 'config.yml')
        if os.path.exists(geyser_config_path):
            with open(geyser_config_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            with open(geyser_config_path, 'w', encoding='utf-8') as f:
                for line in lines:
                    if line.strip().startswith('port:'):
                        f.write(f'  port: {new_bedrock_port}\n')
                    else:
                        f.write(line)
        
    except Exception as e:
        flash(f"サーバーの起動中にエラーが発生しました: {e}", "info")
    
    return redirect(url_for("index"))

@app.route("/stop/<int:port>", methods=["POST"])
def stop_server(port):
    """指定されたポートのサーバーを停止するルート"""
    server_info = running_servers.get(port)
    if server_info and server_info['process'].poll() is None:
        try:
            server_info['process'].stdin.write("stop\n")
            server_info['process'].stdin.flush()
            server_info['process'].wait(timeout=30)
            flash(f"ポート {port} のサーバーが停止しました。", "info")
        except (BrokenPipeError, subprocess.TimeoutExpired) as e:
            server_info['process'].kill()
            flash(f"ポート {port} のサーバーを強制終了しました。", "info")
        finally:
            server_info['process'] = None
    else:
        flash(f"ポート {port} のサーバーは既に停止しています。", "info")
    
    if port in running_servers:
        if os.path.exists(running_servers[port]['path']):
            shutil.rmtree(running_servers[port]['path'])
        del running_servers[port]
        
    return redirect(url_for("index"))

def cleanup_servers():
    """終了したサーバープロセスをリストから削除する"""
    ports_to_remove = []
    for port, server_info in running_servers.items():
        if server_info['process'].poll() is not None:
            ports_to_remove.append(port)
    
    for port in ports_to_remove:
        if os.path.exists(running_servers[port]['path']):
            shutil.rmtree(running_servers[port]['path'])
        del running_servers[port]

if __name__ == "__main__":
    # Codespacesで動作するようにホストを0.0.0.0に設定
    app.run(host='0.0.0.0', port=5000)
