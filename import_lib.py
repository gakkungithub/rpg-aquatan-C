import importlib
import ensurepip
import subprocess
import sys

def ensure_pip():
    """pipが存在しない場合、自動でインストール"""
    try:
        import pip  # すでにあるか確認
        return True
    except ImportError:
        print("⚙️ pip が見つかりません。ensurepipでインストールします...")
        try:
            ensurepip.bootstrap()
            print("✅ pip をセットアップしました。")
            return True
        except Exception as e:
            print("❌ pip のセットアップに失敗しました:", e)
            return False

def ensure_package(package_name, import_name=None):
    """指定したモジュールが存在しない場合、自動でpip installする"""
    if import_name is None:
        import_name = package_name

    try:
        importlib.import_module(import_name)
    except ImportError:
        print(f"🔧 {package_name} が見つかりません。インストールします...")
        if not ensure_pip():
            print(f"❌ pipが利用できないため {package_name} をインストールできません。")
            sys.exit(1)
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        except Exception as e:
            print(f"❌ {package_name} のインストールに失敗しました: {e}")
            sys.exit(1)
    finally:
        globals()[import_name] = importlib.import_module(import_name)