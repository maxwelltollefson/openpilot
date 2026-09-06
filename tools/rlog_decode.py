#!/usr/bin/env python3
"""
rlog_decode.py — reusable openpilot rlog/qlog decoder for WINDOWS.

Openpilot's own Python logreader needs the msgq/cereal scons build (Linux-only),
and pycapnp's Windows wheel aborts compiling the cereal schema. So this tool
shells out to the capnproto CLI (`capnp.exe`), which openpilot itself uses, and
implements the same framing as cereal's read_multiple_bytes().

Framing (identical to capnp StreamFdMessageReader running over a concatenated
buffer — see kj/io.c++, MessageReader::readMessage):
  * read u32 `wordCount`
      - 0                         -> null/empty message, skip (4-byte advance)
      - lower 2 bits of the u32, or bit-31 set, encode the layout — the plain
        form is: `segCount = wordCount + 1`
  * read `segCount` u32 segment sizes in 8-byte WORDS
  * skip `sum(sizes)` words of message body
  * each message is padded to 8 bytes (wordCount and sizes and body are all
    word-quantized, so this is automatic)

Usage:
    python tools/rlog_decode.py <file.zst|file.rlog> [--match SUBSTR]
    python tools/rlog_decode.py <file> --types          # just the event histogram

Prefer passing the original `.zst`; the tool decompresses in memory.
"""
import os
import re
import struct
import subprocess
import sys
import zstandard as zstd

# ---- locate capnp.exe and the schema ----
CAPNP_CANDIDATES = [
    r"C:\Users\Leon\AppData\Local\Microsoft\WinGet\Packages\capnproto.capnproto_Microsoft.Winget.Source_8wekyb3d8bbwe\capnproto-tools-win32-1.1.0\capnp.exe",
    r"C:\Users\Leon\.ogs-meshery-tools\Library\bin\capnp.exe",
]
SCHEMA_CANDIDATES = [
    r"C:\Users\Leon\AppData\Local\Temp\capnp_stage\log.capnp",
    r"C:\Users\Leon\caravan-port\carnival-fork\cereal\log.capnp",
]

CAPNP = next((c for c in CAPNP_CANDIDATES if os.path.exists(c)), None)
SCHEMA = next((c for c in SCHEMA_CANDIDATES if os.path.exists(c)), None)
if not CAPNP:
    sys.exit("capnp.exe not found; install via `winget install capnproto.capnproto`")
if not SCHEMA:
    sys.exit("cereal log.capnp not found")


def decompress(data: bytes) -> bytes:
    if data.startswith(b"\x28\xB5\x2F\xFD"):
        dctx = zstd.ZstdDecompressor()
        with dctx.stream_reader(data) as reader:
            return reader.read()
    return data


def iter_messages(data: bytes):
    """Yield (offset, raw_capnp_message_bytes) per cereal read_multiple_bytes framing."""
    n = len(data)
    off = 0
    while off + 4 <= n:
        word_count = struct.unpack_from("<I", data, off)[0]
        if word_count == 0xFFFFFFFF:
            break
        if word_count & 0x80000000:  # single-segment shortcut
            seg_count = 1
            seg_sizes = [word_count & 0x7FFFFFFF]
        else:
            # cereal framing: word_count stores (segmentCount - 1)
            seg_count = word_count + 1
            if seg_count > 32:
                # not a valid header word — skip a word (handles 4-byte inter-message pad)
                off += 4
                continue
            if off + 4 + 4 * seg_count > n:
                off += 4
                continue
            seg_sizes = struct.unpack_from("<" + "I" * seg_count, data, off + 4)
        header = 4 + 4 * seg_count
        body_words = sum(seg_sizes)
        if body_words == 0:
            # empty/null message — skip header
            off += header
            continue
        body = header + body_words * 8
        if off + body > n:
            off += 4
            continue
        yield off, data[off:off + body]
        off += body


def decode_one(raw: bytes) -> str:
    p = subprocess.run([CAPNP, "decode", SCHEMA, "Event"],
                       input=raw, capture_output=True, timeout=20)
    return p.stdout.decode("utf-8", errors="replace")


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    path = sys.argv[1]
    args = sys.argv[2:]
    match = None
    # extract --match SUBSTR
    if "--match" in args:
        i = args.index("--match")
        if i + 1 < len(args):
            match = args[i + 1]
    data = decompress(open(path, "rb").read())

    from collections import Counter
    type_counter = Counter()
    firsts = {}          # field name -> decoded text of first occurrence
    canvalid = []        # (event_idx, canValid, canTimeout, canErrorCounter)
    matched = []

    for idx, (off, raw) in enumerate(iter_messages(data)):
        txt = decode_one(raw)
        m = re.match(r"^\(([a-zA-Z]+) =", txt)
        if not m:
            continue
        w = m.group(1)
        type_counter[w] += 1
        if w not in firsts:
            firsts[w] = txt
        if match and match.lower() in txt.lower():
            matched.append((idx, w, txt))
        if w == "carState":
            mv = re.search(r"canValid = (\w+)", txt)
            mt = re.search(r"canTimeout = (\w+)", txt)
            mc = re.search(r"canErrorCounter = (\d+)", txt)
            canvalid.append((idx, mv.group(1) if mv else "?",
                             mt.group(1) if mt else "?", mc.group(1) if mc else "?"))

    print(f"decoded {sum(type_counter.values())} messages from {os.path.basename(path)}")
    print("\n=== event-type histogram ===")
    for k, v in type_counter.most_common(50):
        print(f"  {v:8d}  {k}")

    if "carParams" in firsts:
        t = firsts["carParams"]
        print("\n=== carParams ===")
        for f in ["carName", "carFingerprint", "vin", "minEnableSpeed",
                  "pcmCruise", "radarUnavailable", "openpilotLongitudinalControl"]:
            mm = re.search(rf'{f} = "?([^"\n)]*)', t)
            if mm:
                print(f"  {f}: {mm.group(1)}")

    if "pandaStates" in firsts:
        t = firsts["pandaStates"]
        print("\n=== pandaStates[0] ===")
        for f in ["safetyModel", "safetyParam", "controlsAllowed", "safetyRxInvalid",
                  "ignitionCan", "pandaType", "safetyMode", "faultStatus"]:
            mm = re.search(rf'{f} = (\w+)', t)
            if mm:
                print(f"  {f}: {mm.group(1)}")

    if canvalid:
        print("\n=== carState canValid (first 6 + every transition) ===")
        last = None; shown = 0
        for idx, v, t, c in canvalid:
            if v != last or shown < 6:
                print(f"  msg {idx:6d}: canValid={v} canTimeout={t} canErrorCounter={c}")
                last = v; shown += 1

    if matched:
        print(f"\n=== {len(matched)} messages matching {match!r} ===")
        for idx, w, txt in matched[:20]:
            print(f"\n--- msg {idx} [{w}] ---")
            print(txt[:2000])


if __name__ == "__main__":
    main()
