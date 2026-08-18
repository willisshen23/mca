"""LLM API Key 密文配置运维工具（AES-256-GCM，与 src/secrets.py 配套）。

用法（在 backend 目录下，或任意目录指定 --env）：

    # 1. 生成主密钥（写入 backend/data/secrets/master.key，chmod 600）
    python scripts/env_secret.py init

    # 2. 把 backend/.env 中 LLM_API_KEY / 所有 *_LLM_API_KEY 明文就地替换为密文
    python scripts/env_secret.py encrypt

    # 3. 校验：所有 enc:v1: 值可解密、无残留明文
    #    （--require-encrypted 严格模式）
    python scripts/env_secret.py check [--require-encrypted]

    # 4. 审计查看明文（注意会输出密钥，仅限受控环境）
    python scripts/env_secret.py decrypt

    # 5. 轮换主密钥：旧 key 解密 → 新 key 重加密（--generate-new 自动生成）
    python scripts/env_secret.py rotate --generate-new [--old-key-file /path/old.key]

主密钥解析优先级：--key > --key-file > 环境变量 LLM_MASTER_KEY >
LLM_MASTER_KEY_FILE > 默认 backend/data/secrets/master.key。
主密钥必须与密文物理分离（不要写进 backend/.env 同一文件）。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.secrets import (  # noqa: E402
    ENC_PREFIX,
    decrypt,
    encrypt,
    generate_master_key,
    load_master_key,
    looks_encrypted,
    normalize_master_key,
)

DEFAULT_ENV_FILE = ROOT / ".env"
DEFAULT_KEY_FILE = ROOT / "data" / "secrets" / "master.key"

_ENV_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*)$")


# ── .env 行级编辑（保留注释/空行/无关行原样） ──


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _quote_style(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[0]
    return ""


def _target_fields(fields_arg: str | None) -> set[str] | None:
    """None → 匹配 LLM_API_KEY 及所有 *_LLM_API_KEY；否则用逗号列表。"""
    if fields_arg is None:
        return None
    return {f.strip().upper() for f in fields_arg.split(",") if f.strip()}


def _is_target(key: str, fields: set[str] | None) -> bool:
    upper = key.upper()
    if fields is not None:
        return upper in fields
    # 注意：LLM_API_KEY 本身不以 _LLM_API_KEY 结尾，需单独匹配
    return upper == "LLM_API_KEY" or upper.endswith("_LLM_API_KEY")


def _resolve_key(args: argparse.Namespace, attr: str = "key") -> bytes | None:
    """--key/--key-file → 环境变量 → 默认密钥文件。"""
    raw = getattr(args, attr, None) or getattr(args, f"{attr}_file", None)
    if raw:
        if getattr(args, f"{attr}_file", None):
            path = Path(getattr(args, f"{attr}_file"))
            if not path.is_file():
                raise SystemExit(f"密钥文件不存在: {path}")
            return normalize_master_key(path.read_text(encoding="utf-8"))
        return normalize_master_key(raw)
    return load_master_key(default_key_file=DEFAULT_KEY_FILE)


def _read_env_lines(path: Path) -> list[str]:
    if not path.is_file():
        raise SystemExit(f".env 文件不存在: {path}")
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def _write_env_lines(path: Path, lines: list[str]) -> None:
    path.write_text("".join(lines), encoding="utf-8")


def _new_value(value: str, ciphertext: str) -> str:
    quote = _quote_style(value)
    return f"{quote}{ciphertext}{quote}"


# ── 子命令 ──


def cmd_init(args: argparse.Namespace) -> None:
    key = generate_master_key()
    if args.print:
        print(key.hex())
        return
    path = Path(args.file)
    if path.exists() and not args.force:
        raise SystemExit(f"密钥文件已存在（防止覆盖）: {path}（用 --force 覆盖）")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key.hex() + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows 无 POSIX 权限模型，忽略
    print(f"主密钥已写入 {path}（chmod 600）")
    print(
        "请妥善保管：部署时通过环境变量 LLM_MASTER_KEY 或 "
        "LLM_MASTER_KEY_FILE 注入，切勿与密文同文件。"
    )


def cmd_encrypt(args: argparse.Namespace) -> None:
    key = _resolve_key(args)
    if key is None:
        raise SystemExit(
            "缺少主密钥：请用 --key / --key-file 或环境变量 LLM_MASTER_KEY 提供"
        )
    env_file = Path(args.env)
    fields = _target_fields(args.fields)
    lines = _read_env_lines(env_file)
    changed, skipped, plain_left = 0, 0, 0
    for i, line in enumerate(lines):
        m = _ENV_LINE_RE.match(line.rstrip("\r\n"))
        if not m or not _is_target(m.group(1), fields):
            continue
        value = _strip_quotes(m.group(3).strip())
        if not value:
            continue
        if looks_encrypted(value):
            skipped += 1
            continue
        ciphertext = encrypt(value, key)
        lines[i] = f"{m.group(1)}{m.group(2)}{_new_value(m.group(3).strip(), ciphertext)}\n"
        changed += 1
        plain_left += 1
    if changed:
        _write_env_lines(env_file, lines)
    print(
        f"{env_file}: 加密 {changed} 个字段，跳过已加密 {skipped} 个，"
        f"明文残留 {plain_left} 个"
    )


def cmd_check(args: argparse.Namespace) -> None:
    env_file = Path(args.env)
    fields = _target_fields(args.fields)
    lines = _read_env_lines(env_file)
    key = _resolve_key(args)
    errors: list[str] = []
    enc_count = 0
    for line in lines:
        m = _ENV_LINE_RE.match(line.rstrip("\r\n"))
        if not m or not _is_target(m.group(1), fields):
            continue
        value = _strip_quotes(m.group(3).strip())
        if not value:
            continue
        if looks_encrypted(value):
            enc_count += 1
            try:
                if key is None:
                    raise SystemExit(
                        f"{m.group(1)} 为密文但未提供主密钥"
                        "（--key/--key-file/环境变量）"
                    )
                decrypt(value, key)
                print(f"  [ok] {m.group(1)} 密文可解密")
            except SystemExit:
                raise
            except Exception as exc:
                errors.append(f"{m.group(1)}: {exc}")
        elif args.require_encrypted:
            errors.append(f"{m.group(1)}: 仍是明文（--require-encrypted 模式）")
    if errors:
        for e in errors:
            print(f"  [fail] {e}", file=sys.stderr)
        raise SystemExit(1)
    summary = f"{env_file}: 全部 {enc_count} 个密文字段可解密"
    if args.require_encrypted:
        summary += "，无明文残留"
    print(summary)


def cmd_decrypt(args: argparse.Namespace) -> None:
    env_file = Path(args.env)
    fields = _target_fields(args.fields)
    lines = _read_env_lines(env_file)
    key = _resolve_key(args)
    for line in lines:
        m = _ENV_LINE_RE.match(line.rstrip("\r\n"))
        if not m or not _is_target(m.group(1), fields):
            continue
        value = _strip_quotes(m.group(3).strip())
        if not value:
            continue
        plain = _maybe_decrypt_safe(value, key, m.group(1))
        print(f"{m.group(1)}={plain}")


def _maybe_decrypt_safe(value: str, key: bytes | None, name: str) -> str:
    if not looks_encrypted(value):
        return value
    if key is None:
        raise SystemExit(f"{name} 为密文但未提供主密钥")
    try:
        return decrypt(value, key)
    except Exception as exc:
        raise SystemExit(f"{name}: {exc}") from exc


def cmd_rotate(args: argparse.Namespace) -> None:
    env_file = Path(args.env)
    fields = _target_fields(args.fields)
    lines = _read_env_lines(env_file)
    old_key = _resolve_key(args, attr="old_key")
    if args.generate_new:
        new_key = generate_master_key()
        print(f"已生成新主密钥: {new_key.hex()}（请安全保管并部署）")
    else:
        new_key = _resolve_key(args, attr="new_key")
        if new_key is None:
            raise SystemExit("缺少新主密钥：--new-key / --new-key-file 或 --generate-new")
    changed, skipped = 0, 0
    for i, line in enumerate(lines):
        m = _ENV_LINE_RE.match(line.rstrip("\r\n"))
        if not m or not _is_target(m.group(1), fields):
            continue
        value = _strip_quotes(m.group(3).strip())
        if not value or not looks_encrypted(value):
            continue
        if old_key is None:
            raise SystemExit(
                f"{m.group(1)} 为密文但未提供旧主密钥（--old-key/--old-key-file）"
            )
        plain = decrypt(value, old_key)
        lines[i] = f"{m.group(1)}{m.group(2)}{_new_value(value, encrypt(plain, new_key))}\n"
        changed += 1
        skipped += 1
    if changed:
        _write_env_lines(env_file, lines)
    print(f"{env_file}: 用新主密钥重加密 {changed} 个字段，跳过明文 {skipped} 个")


# ── argparse ──


def _add_key_args(p: argparse.ArgumentParser, attr: str) -> None:
    opt = attr.replace("_", "-")  # 选项用连字符（如 --old-key），dest 保留下划线
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        f"--{opt}",
        dest=attr,
        metavar="KEY",
        help=f"{attr} 主密钥（hex 64 或 base64 44 字符）",
    )
    g.add_argument(
        f"--{opt}-file",
        dest=f"{attr}_file",
        metavar="PATH",
        help=f"{attr} 主密钥文件路径",
    )


def _add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--env",
        default=str(DEFAULT_ENV_FILE),
        help=f".env 路径（默认 {DEFAULT_ENV_FILE}）",
    )
    p.add_argument(
        "--fields",
        help="逗号分隔字段名（默认 LLM_API_KEY 及所有 *_LLM_API_KEY）",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="生成新的 32 字节主密钥")
    p.add_argument(
        "--file",
        default=str(DEFAULT_KEY_FILE),
        help=f"密钥文件路径（默认 {DEFAULT_KEY_FILE}）",
    )
    p.add_argument("--print", action="store_true", help="只打印密钥到 stdout，不写文件")
    p.add_argument("--force", action="store_true", help="覆盖已存在的密钥文件")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("encrypt", help="把 .env 中 LLM API Key 明文就地替换为密文")
    _add_common_args(p)
    _add_key_args(p, "key")
    p.set_defaults(func=cmd_encrypt)

    p = sub.add_parser("check", help="校验 .env 密文均可解密")
    _add_common_args(p)
    p.add_argument(
        "--require-encrypted",
        action="store_true",
        help="严格模式：目标字段不允许明文残留",
    )
    _add_key_args(p, "key")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser(
        "decrypt",
        help="打印 .env 目标字段明文（审计用，注意输出敏感信息）",
    )
    _add_common_args(p)
    _add_key_args(p, "key")
    p.set_defaults(func=cmd_decrypt)

    p = sub.add_parser("rotate", help="用新主密钥重加密 .env 中的密文")
    _add_common_args(p)
    _add_key_args(p, "old_key")
    _add_key_args(p, "new_key")
    p.add_argument("--generate-new", action="store_true", help="自动生成新主密钥并打印")
    p.set_defaults(func=cmd_rotate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
