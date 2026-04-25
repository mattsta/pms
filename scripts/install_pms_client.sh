#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLIENT_DIR="$ROOT_DIR/client-rust"
BIN_DIR="$ROOT_DIR/.bin"
TARGET_BIN="$BIN_DIR/pms-client"
SERVER_URL="${PMS_SERVER_BASE_URL:-http://127.0.0.1:27541}"
PRINT_ENV=0
SKIP_SIGN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --print-env)
      PRINT_ENV=1
      shift
      ;;
    --no-sign)
      SKIP_SIGN=1
      shift
      ;;
    --bin-dir)
      BIN_DIR="$2"
      TARGET_BIN="$BIN_DIR/pms-client"
      shift 2
      ;;
    --server-url)
      SERVER_URL="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 [--print-env] [--no-sign] [--bin-dir <dir>] [--server-url <url>]" >&2
      exit 2
      ;;
  esac
done

mkdir -p "$BIN_DIR"

(
  cd "$CLIENT_DIR"
  cargo build --release --quiet
)

SOURCE_BIN="$CLIENT_DIR/target/release/pms-client"
TEMP_BIN="$TARGET_BIN.tmp"

install -m 755 "$SOURCE_BIN" "$TEMP_BIN"
if ! cmp -s "$SOURCE_BIN" "$TEMP_BIN"; then
  echo "Installed binary temp copy does not match release artifact" >&2
  echo "  source: $SOURCE_BIN" >&2
  echo "  target: $TEMP_BIN" >&2
  exit 1
fi
mv -f "$TEMP_BIN" "$TARGET_BIN"

if [[ "$SKIP_SIGN" -eq 0 ]] && [[ "$(uname -s)" == "Darwin" ]] && command -v codesign >/dev/null 2>&1; then
  if ! codesign --force --sign - "$TARGET_BIN" >/dev/null 2>&1; then
    echo "Warning: ad-hoc codesign failed for $TARGET_BIN" >&2
  elif ! codesign --verify "$TARGET_BIN" >/dev/null 2>&1; then
    echo "Installed binary failed codesign verification" >&2
    echo "  target: $TARGET_BIN" >&2
    exit 1
  fi
elif ! cmp -s "$SOURCE_BIN" "$TARGET_BIN"; then
  echo "Installed binary does not match release artifact" >&2
  echo "  source: $SOURCE_BIN" >&2
  echo "  target: $TARGET_BIN" >&2
  exit 1
fi

echo "Installed: $TARGET_BIN"
echo "Server URL: $SERVER_URL"
echo "Suggested alternate prefix:"
echo "  $TARGET_BIN --server $SERVER_URL"
echo
echo "Suggested shell exports:"
echo "  export PATH=\"$BIN_DIR:\$PATH\""
echo "  export PMS_ALT_CLI_ARGV0=\"$TARGET_BIN --server $SERVER_URL\""

if [[ "$PRINT_ENV" -eq 1 ]]; then
  echo
  echo "PATH=\"$BIN_DIR:\$PATH\""
  echo "PMS_ALT_CLI_ARGV0=\"$TARGET_BIN --server $SERVER_URL\""
fi
