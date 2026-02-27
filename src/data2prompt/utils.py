import os
import sys
import tiktoken

def count_tokens(text, encoding_name="o200k_base"):
    """Returns the number of tokens in a text string."""
    try:
        encoding = tiktoken.get_encoding(encoding_name)
        num_tokens = len(encoding.encode(text))
        return num_tokens
    except Exception:
        return 0

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

def load_ignore_file(directory):
    """
    Looks for a .data2promptignore file in the given directory.
    Returns a list of patterns to ignore, excluding comments and empty lines.
    """
    ignore_path = os.path.join(directory, '.data2promptignore')
    ignore_list = []
    
    if os.path.exists(ignore_path):
        try:
            with open(ignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    # Strip trailing slashes and whitespace
                    pattern = line.rstrip('/')
                    ignore_list.append(pattern)
        except Exception as e:
            print(f"⚠️  Warning: Could not read .data2promptignore: {e}")
            
    return ignore_list
