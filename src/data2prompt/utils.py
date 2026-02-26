import os
import sys

def print_header():
    header = """
    ==============================================
        📊 DATA PROJECT -> LLM PROMPT PACKAGER 📊
    ==============================================
    """
    print(header)

def get_status_msg(file_path, file_count):
    sys.stdout.write(f"\r[#{file_count}] Processing: {file_path[:50]}...".ljust(70))
    sys.stdout.flush()

def is_binary(file_path):
    """Check if a file is binary by looking for a Null byte in the first 1024 bytes."""
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(1024)
            return b'\0' in chunk
    except Exception:
        return False

def generate_tree(startpath, ignore_folders, ignore_files):
    tree = []
    for root, dirs, files in os.walk(startpath):
        dirs[:] = [d for d in dirs if d not in ignore_folders]
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * level
        tree.append(f"{indent}📂 {os.path.basename(root)}/")
        sub_indent = ' ' * 4 * (level + 1)
        for f in files:
            if f not in ignore_files:
                tree.append(f"{sub_indent}📄 {f}")
    return "\n".join(tree)
