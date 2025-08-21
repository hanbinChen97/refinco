# Python 包、导入与 .env 使用指南（RefinCo 项目）

这份文档用通俗的方式说明：在本项目里，如何正确组织包(package)、书写导入(import)，以及如何加载 `.env` 环境变量；尤其是“文件夹中间互相调用”和“直接运行某个脚本”时该怎么做。

---

## 你需要记住的 5 条规则（TL;DR）

1. `.env` 放在项目根目录（与 `README.md` 同级）。
2. 运行脚本优先用包方式：`python -m utils.enhance_info_with_perplexity`（或 `uv run -m utils.enhance_info_with_perplexity`）。
3. 代码里使用“绝对导入”：`from utils.perplexity_llm import perplexity_generate_text`。
4. CLI 入口在 `if __name__ == "__main__":` 中，启动时尽早 `load_dotenv(...)` 加载环境变量。
5. 如果“直接用路径运行某个文件”，在该文件里用一小段 shim 把项目根加入 `sys.path`，保证 `utils` 能被当作包解析。

---

## 项目结构与包识别

本项目关键部分：

```
refinco/
├── README.md
├── .env                 # 建议放在这里
├── utils/
│   ├── __init__.py      # 让 utils 成为一个 Python 包
│   ├── perplexity_llm.py
│   └── enhance_info_with_perplexity.py
└── ...
```

- 有了 `utils/__init__.py`，`utils` 才是“包（package）”。
- 当你“在项目根目录下”用 `python -m utils.enhance_info_with_perplexity` 运行时，Python 会把项目根目录加入 `sys.path`，因此 `from utils.xxx import ...` 能正常解析。

## 绝对导入 vs 相对导入

- 推荐本项目使用“绝对导入”（更稳定、可读）：
  ```python
  from utils.perplexity_llm import perplexity_generate_text
  ```
- 不建议在顶层脚本里使用相对导入（`from .perplexity_llm import ...`），因为当脚本直接运行时，它可能不是在包上下文里。

## 两种运行方式

1) 包方式（推荐）

- 在项目根目录运行，保证包导入最干净：
  ```bash
  uv run -m utils.enhance_info_with_perplexity
  # 或者使用你的 venv
  /path/to/python -m utils.enhance_info_with_perplexity
  ```

2) 直接路径运行（已做兼容）

- 如果你想直接：
  ```bash
  /path/to/python /Users/hanbin/workspace/refinco/utils/enhance_info_with_perplexity.py
  ```
- 这种情况下，该文件不是在包上下文里，`from utils...` 可能会失败。为此我们在文件里面加了一个很小的 shim：
  ```python
  if __name__ == "__main__" and __package__ is None:
      import sys as _sys, os as _os
      _project_root = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), _os.pardir))
      if _project_root not in _sys.path:
          _sys.path.insert(0, _project_root)
  ```
- 这样做的作用：在“直跑”时，手动把项目根目录加入 `sys.path`，让 `utils` 能被识别为包。包方式运行时不会触发这段逻辑。

## .env 与 load_dotenv 的正确打开方式

- `.env` 的位置：项目根目录（和 `README.md` 同级）。
- 使用 `python-dotenv` 提供的 `find_dotenv()` + `load_dotenv()`：
  ```python
  from dotenv import load_dotenv, find_dotenv
  load_dotenv(find_dotenv())  # 在可能的搜索路径里寻找 .env 并加载
  ```
- 若担心找不到，则可以追加一个“回退路径”（fallback），比如相对于当前文件向上找项目根目录的 `.env`：
  ```python
  import os
  if not os.getenv("PERPLEXITY_API_KEY"):
      project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
      env_path = os.path.join(project_root, ".env")
      if os.path.exists(env_path):
          load_dotenv(env_path)
  ```
- 调用时机：尽量“越早越好”。
  - CLI 入口（`if __name__ == "__main__":`）或模块顶部调用都可以。
  - 我们在 `utils/enhance_info_with_perplexity.py` 顶部调用，确保无论以哪种方式运行都能加载到环境变量。
- `load_dotenv` 多次调用是安全的（幂等），因此模块 A 和 B 同时加载 `.env` 也没问题。

## 常见错误与快速排查

1) `ModuleNotFoundError: No module named 'utils.perplexity_llm'; 'utils' is not a package`
   - 原因：直接用路径运行脚本，且没有把项目根加入 `sys.path`。
   - 解决：
     - 使用包方式运行：`python -m utils.enhance_info_with_perplexity`；或
     - 保持我们在脚本内的 shim 代码；或
     - 在终端临时设置 `PYTHONPATH` 指向项目根（不推荐，易忘）。

2) `SKIP: PERPLEXITY_API_KEY not set ...`
   - 原因：没有加载到 `.env`，或 `.env` 中未配置键值。
   - 解决：
     - 确保 `.env` 在项目根；
     - `.env` 中包含 `PERPLEXITY_API_KEY=你的key`；
     - 运行入口足够早地调用 `load_dotenv(...)`（我们已在模块顶部处理）。

3) 在 Notebook 或其它工作目录里运行
   - 现象：`find_dotenv()` 找不到 `.env`，或绝对导入失败。
   - 方案：
     - 在 Notebook 的第一个单元格手动 `sys.path.insert(0, PROJECT_ROOT)`；
     - 或使用 `%load_ext dotenv; %dotenv /path/to/.env`；
     - 项目代码中保留顶部的 `find_dotenv()` + fallback 逻辑，兼容多种工作目录。

## 推荐样板（可复制使用）

以 `utils/enhance_info_with_perplexity.py` 为例，关键几行：

```python
from dotenv import load_dotenv, find_dotenv
import os

# 1) 早加载 .env
load_dotenv(find_dotenv())
if not os.getenv("PERPLEXITY_API_KEY"):
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    env_path = os.path.join(project_root, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)

# 2) 兼容直接路径运行
if __name__ == "__main__" and __package__ is None:
    import sys as _sys
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    if project_root not in _sys.path:
        _sys.path.insert(0, project_root)

# 3) 使用绝对导入
from utils.perplexity_llm import perplexity_generate_text
```

运行方式：

```bash
# 推荐
uv run -m utils.enhance_info_with_perplexity

# 或者（已兼容）
/path/to/python /Users/hanbin/workspace/refinco/utils/enhance_info_with_perplexity.py
```

## 小结

- 把 `.env` 固定放在项目根，入口尽早 `load_dotenv`。
- 统一使用绝对导入（`from utils...`）。
- 优先使用 `-m` 包方式运行；必须直跑时，文件内加一个 5 行的 sys.path shim 即可。

遇到具体导入或环境问题，可以把你的运行命令和报错贴出来；按上面的“常见错误与排查”逐条对照，很快能定位。祝开发顺利！
