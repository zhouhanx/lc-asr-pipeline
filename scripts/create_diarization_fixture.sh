#!/bin/sh

set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUTPUT_DIR="$PROJECT_ROOT/data/fixtures"
OUTPUT_FILE="$OUTPUT_DIR/two-speaker-zh.wav"
TEMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/lc-asr-diarization.XXXXXX")
trap 'rm -rf "$TEMP_DIR"' EXIT HUP INT TERM

mkdir -p "$OUTPUT_DIR"
say -v Tingting -r 165 -o "$TEMP_DIR/a1.aiff" \
    '你好，我是今天的面试官，请先介绍一下你的工作经历。'
say -v Sinji -r 165 -o "$TEMP_DIR/b1.aiff" \
    '您好，我有五年的软件开发经验，主要负责数据平台。'
say -v Tingting -r 165 -o "$TEMP_DIR/a2.aiff" \
    '请说明你在项目中遇到过的最大挑战。'
say -v Sinji -r 165 -o "$TEMP_DIR/b2.aiff" \
    '最大的挑战是系统迁移，我通过分阶段发布降低了风险。'

ffmpeg -hide_banner -loglevel error -y \
    -i "$TEMP_DIR/a1.aiff" -i "$TEMP_DIR/b1.aiff" \
    -i "$TEMP_DIR/a2.aiff" -i "$TEMP_DIR/b2.aiff" \
    -filter_complex \
    '[0:a]aresample=16000,aformat=sample_fmts=s16:channel_layouts=mono[a0];
     [1:a]aresample=16000,aformat=sample_fmts=s16:channel_layouts=mono[a1];
     [2:a]aresample=16000,aformat=sample_fmts=s16:channel_layouts=mono[a2];
     [3:a]aresample=16000,aformat=sample_fmts=s16:channel_layouts=mono[a3];
     anullsrc=r=16000:cl=mono:d=0.7[s0];
     anullsrc=r=16000:cl=mono:d=0.7[s1];
     anullsrc=r=16000:cl=mono:d=0.7[s2];
     [a0][s0][a1][s1][a2][s2][a3]concat=n=7:v=0:a=1[out]' \
    -map '[out]' -ar 16000 -ac 1 "$OUTPUT_FILE"

printf 'fixture=%s\n' "$OUTPUT_FILE"
