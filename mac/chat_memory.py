#!/usr/bin/env python3
"""
chat 记忆模块：原子事实提取 + 关键词检索
用法:
  chat_memory.py extract <ollama_url> <user_msg> <assistant_msg> <session>
  chat_memory.py search  <query> [--top N]
"""
import sys, json, os, re, time
from pathlib import Path
from datetime import datetime
import urllib.request, urllib.error

MEMORY_FILE = Path.home() / ".chat_memory" / "facts.jsonl"
MEMORY_FILE.parent.mkdir(exist_ok=True)

STOP_WORDS = {
    "的", "了", "是", "在", "我", "你", "他", "她", "它", "们",
    "和", "与", "或", "但", "而", "也", "都", "就", "能", "会",
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "i", "you", "he", "she", "it", "we", "they", "and", "or",
    "but", "in", "on", "at", "to", "for", "of", "with", "this",
    "that", "have", "has", "do", "does", "can", "will", "what",
    "how", "why", "when", "where", "which",
}

def tokenize(text: str) -> set[str]:
    """Split text into searchable tokens; CJK strings → unigrams + bigrams."""
    tokens = set()
    for m in re.findall(r'[a-zA-Z0-9]+|[一-鿿]+', text.lower()):
        if re.match(r'[一-鿿]', m):
            for i in range(len(m)):
                tokens.add(m[i])
            for i in range(len(m) - 1):
                tokens.add(m[i:i+2])
        else:
            tokens.add(m)
    return tokens - STOP_WORDS

# ── 提取事实 ────────────────────────────────────────────────────────────
def extract(ollama_url: str, user_msg: str, assistant_msg: str, session: str):
    prompt = f"""Extract 1-3 key facts from the conversation below. Write facts in the SAME LANGUAGE as the conversation (keep technical terms, names, code, and proper nouns in their original form). Each fact must be a single short sentence capturing important information (user preferences, technical decisions, project details, names, etc.). Output each fact on its own line. If there are no important facts worth remembering, output exactly: none

User: {user_msg[:400]}
Assistant: {assistant_msg[:400]}

Facts (one per line, or "none"):"""

    body = json.dumps({
        "model": "gemma4",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0, "num_predict": 500}
    }).encode()

    try:
        req = urllib.request.Request(
            f"{ollama_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.load(r)
        raw = resp.get("message", {}).get("content", "").strip()
    except Exception as e:
        print(f"[memory] extract failed: {e}", file=sys.stderr)
        return

    # 去掉引号后判断 none
    clean = raw.strip("'\"`").lower()
    if not raw or clean in ("none", "no facts", "nothing", "no relevant facts", "n/a"):
        return

    ts = datetime.now().isoformat(timespec="seconds")
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        for line in raw.splitlines():
            line = line.strip().lstrip("-*•123456789. ")
            if len(line) > 8:
                entry = {"fact": line, "session": session, "ts": ts}
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                print(f"[memory] +fact: {line[:60]}", file=sys.stderr)

# ── 搜索相关事实 ────────────────────────────────────────────────────────
def search(query: str, top: int = 5) -> list[str]:
    if not MEMORY_FILE.exists():
        return []

    query_words = tokenize(query)
    if not query_words:
        return []

    scored = []
    with open(MEMORY_FILE, encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    # 只检索最近 1000 条
    for line in lines[-1000:]:
        try:
            entry = json.loads(line)
        except Exception:
            continue
        fact = entry.get("fact", "")
        fact_words = tokenize(fact)
        overlap = len(query_words & fact_words)
        if overlap > 0:
            scored.append((overlap, entry.get("ts", ""), fact))

    scored.sort(reverse=True)
    # 去重（相同事实只保留一次）
    seen, results = set(), []
    for _, _, fact in scored:
        key = fact[:50]
        if key not in seen:
            seen.add(key)
            results.append(fact)
        if len(results) >= top:
            break
    return results

# ── 入口 ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""

    if cmd == "extract":
        # extract <ollama_url> <user_msg> <assistant_msg> <session>
        ollama_url  = sys.argv[2]
        user_msg    = sys.argv[3]
        assistant_msg = sys.argv[4]
        session     = sys.argv[5] if len(sys.argv) > 5 else "default"
        extract(ollama_url, user_msg, assistant_msg, session)

    elif cmd == "search":
        query = sys.argv[2]
        top   = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        facts = search(query, top)
        # 输出为 JSON 数组，供 shell 解析
        print(json.dumps(facts, ensure_ascii=False))

    elif cmd == "list":
        if MEMORY_FILE.exists():
            with open(MEMORY_FILE, encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        print(f"[{d.get('ts','')}] ({d.get('session','')}) {d['fact']}")
                    except Exception:
                        pass
        else:
            print("(空)")

    elif cmd == "clear":
        if MEMORY_FILE.exists():
            MEMORY_FILE.unlink()
            print("记忆已清空")

    else:
        print(__doc__)
        sys.exit(1)
